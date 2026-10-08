import asyncio
from builtins import abs, dict, Exception, float, int, len, list, max, min, round, str, sum, zip
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import aiohttp
from dotenv import load_dotenv
import websockets

# --- ENVIRONMENT & SECURITY SETUP ---
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY", "YOUR_BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "YOUR_BINANCE_SECRET_KEY")

SYMBOL_REST = "SOLUSDT"  # REST requires UPPERCASE
SYMBOL_WS = "solusdt"  # WebSocket streams require lowercase

BASE_URL = "https://api.binance.com"
WS_URL = f"wss://stream.binance.com:9443/ws/{SYMBOL_WS}@depth10@100ms"

# --- STRATEGY HYPERPARAMETERS ---
ATR_MIN_THRESHOLD = 0.03
SL_ATR_MULT = 0.5
TP_ATR_MULT = 1.5
OBI_BUY_THRESHOLD = 0.20  # Bids outnumber asks by >20%
OBI_SELL_THRESHOLD = -0.20  # Asks outnumber bids by >20%
CASH_ALLOCATION_PCT = 0.95

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


# --- LOCAL ORDER BOOK STORAGE ---
class BinanceLocalOrderBook:

    def __init__(self):
        self.bids = {}  # {price (float): qty (float)}
        self.asks = {}  # {price (float): qty (float)}

    def apply_snapshot(self, snapshot):
        self.bids = {
            float(price): float(qty) for price, qty in snapshot["bids"]
        }
        self.asks = {
            float(price): float(qty) for price, qty in snapshot["asks"]
        }

    def update_depth(self, bids_data, asks_data):
        self.bids = {float(price): float(qty) for price, qty in bids_data}
        self.asks = {float(price): float(qty) for price, qty in asks_data}

    def get_top_of_book(self):
        if not self.bids or not self.asks:
            return None, None
        return max(self.bids.keys()), min(self.asks.keys())

    def get_order_book_imbalance(self) -> float:
        total_bid_vol = sum(self.bids.values())
        total_ask_vol = sum(self.asks.values())
        total_vol = total_bid_vol + total_ask_vol
        if total_vol == 0:
            return 0.0
        return (total_bid_vol - total_ask_vol) / total_vol


# --- NETWORK ENGINE & REST SIGNER ---
class BinanceNetworkClient:

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    def _generate_signature(self, params: dict) -> str:
        query_string = urllib.parse.urlencode(params)
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def get_depth_snapshot(
        self, session: aiohttp.ClientSession, symbol: str, limit: int = 100
    ) -> dict:
        url = f"{BASE_URL}/api/v3/depth?symbol={symbol}&limit={limit}"
        async with session.get(url) as response:
            return await response.json()

    async def get_historical_klines(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        interval: str = "1m",
        limit: int = 60,
    ) -> list:
        url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        async with session.get(url) as response:
            return await response.json()

    async def send_signed_order(
        self, session: aiohttp.ClientSession, params: dict
    ) -> dict:
        url = f"{BASE_URL}/api/v3/order"
        params["timestamp"] = int(time.time() * 1000)
        params["signature"] = self._generate_signature(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        async with session.post(
            url, headers=headers, params=params
        ) as response:
            return await response.json()


# --- EXECUTION ENGINE ---
class BinanceExecutionEngine:

    def __init__(
        self,
        network_client: BinanceNetworkClient,
        order_book: BinanceLocalOrderBook,
    ):
        self.client = network_client
        self.order_book = order_book
        self.has_active_trade = False
        self.position_qty = 0.0
        self.target_tp_price = None
        self.target_sl_price = None

    async def evaluate_market_signals(
        self, session: aiohttp.ClientSession, indicators: dict
    ):
        best_bid, best_ask = self.order_book.get_top_of_book()
        if not best_bid or not best_ask:
            return

        ema_short = indicators.get("ema_short")
        ema_long = indicators.get("ema_long")
        vwap = indicators.get("vwap")
        atr = indicators.get("atr")

        # Calculate live Order Book Imbalance directly from book state
        obi = self.order_book.get_order_book_imbalance()
        micro_price = (best_bid + best_ask) / 2.0

        if not self.has_active_trade:
            vwap_valid = micro_price > vwap
            ema_valid = ema_short > ema_long
            atr_valid = atr >= ATR_MIN_THRESHOLD
            obi_valid = obi >= OBI_BUY_THRESHOLD

            if vwap_valid and ema_valid and atr_valid and obi_valid:
                account_balance = await self._get_account_balance(session)
                usable_cash = account_balance * CASH_ALLOCATION_PCT
                order_qty = round(usable_cash / best_ask, 5)

                if order_qty > 0:
                    logging.info(
                        f"[SIGNAL] BUY Signal detected at ${best_ask} | OBI: {obi:.2f}"
                    )
                    await self._execute_buy_order(
                        session, best_ask, order_qty, atr
                    )
        else:
            if best_bid >= self.target_tp_price:
                logging.info(f"[EXIT] Take-Profit reached at ${best_bid}")
                await self._execute_sell_order(session, "TAKE_PROFIT_HIT")

            elif best_bid <= self.target_sl_price:
                logging.info(f"[EXIT] Stop-Loss hit at ${best_bid}")
                await self._execute_sell_order(session, "STOP_LOSS_HIT")

            elif (
                micro_price < vwap
                or ema_short < ema_long
                or obi <= OBI_SELL_THRESHOLD
            ):
                logging.info(f"[EXIT] Reversal signal hit at ${best_bid}")
                await self._execute_sell_order(session, "TREND_REVERSAL")

    async def _execute_buy_order(
        self,
        session: aiohttp.ClientSession,
        entry_price: float,
        qty: float,
        atr: float,
    ):
        params = {
            "symbol": SYMBOL_REST,
            "side": "BUY",
            "type": "MARKET",
            "quantity": str(qty),
        }
        response = await self.client.send_signed_order(session, params)

        if "orderId" in response:
            self.has_active_trade = True
            self.position_qty = qty
            self.target_tp_price = round(entry_price + (atr * TP_ATR_MULT), 2)
            self.target_sl_price = round(entry_price - (atr * SL_ATR_MULT), 2)
            logging.info(
                f"[ORDER FILLED] BUY {qty} @ ${entry_price} | TP: ${self.target_tp_price} | SL: ${self.target_sl_price}"
            )
        else:
            logging.error(
                f"[ORDER FAILED] Could not place buy order: {response}"
            )

    async def _execute_sell_order(
        self, session: aiohttp.ClientSession, reason: str
    ):
        params = {
            "symbol": SYMBOL_REST,
            "side": "SELL",
            "type": "MARKET",
            "quantity": str(self.position_qty),
        }
        response = await self.client.send_signed_order(session, params)

        if "orderId" in response:
            logging.info(
                f"[ORDER FILLED] SELL {self.position_qty} | Reason: {reason}"
            )
            self.has_active_trade = False
            self.position_qty = 0.0
            self.target_tp_price = None
            self.target_sl_price = None
        else:
            logging.error(
                f"[ORDER FAILED] Could not place sell order: {response}"
            )

    async def _get_account_balance(
        self, session: aiohttp.ClientSession
    ) -> float:
        params = {"timestamp": int(time.time() * 1000)}
        params["signature"] = self.client._generate_signature(params)

        headers = {"X-MBX-APIKEY": self.client.api_key}
        url = f"{BASE_URL}/api/v3/account"

        async with session.get(
            url, headers=headers, params=params
        ) as response:
            data = await response.json()
            for asset in data.get("balances", []):
                if asset["asset"] == "USDT":
                    return float(asset["free"])
        return 0.0


# --- KLINE / TECHNICAL INDICATORS COMPUTATION ---
async def compute_indicators(
    client: BinanceNetworkClient, session: aiohttp.ClientSession
) -> dict | None:
    try:
        klines = await client.get_historical_klines(
            session, SYMBOL_REST, interval="1m", limit=60
        )
        closes = [float(kline[4]) for kline in klines]
        highs = [float(kline[2]) for kline in klines]
        lows = [float(kline[3]) for kline in klines]
        volumes = [float(kline[5]) for kline in klines]

        def calculate_ema(values: list[float], window: int) -> float:
            multiplier = 2 / (window + 1)
            result = values[0]
            for value in values[1:]:
                result += (value - result) * multiplier
            return result

        vwap_window = 14
        recent_highs = highs[-vwap_window:]
        recent_lows = lows[-vwap_window:]
        recent_closes = closes[-vwap_window:]
        recent_volumes = volumes[-vwap_window:]
        typical_prices = [
            (high + low + close) / 3
            for high, low, close in zip(
                recent_highs, recent_lows, recent_closes
            )
        ]
        volume_total = sum(recent_volumes)
        vwap = (
            sum(price * volume for price, volume in zip(typical_prices, recent_volumes))
            / volume_total
            if volume_total
            else closes[-1]
        )

        true_ranges = [
            max(high - low, abs(high - previous_close), abs(low - previous_close))
            for high, low, previous_close in zip(highs[1:], lows[1:], closes[:-1])
        ]
        atr = sum(true_ranges[-vwap_window:]) / min(
            vwap_window, len(true_ranges)
        )
        return {
            "ema_short": calculate_ema(closes, 9),
            "ema_long": calculate_ema(closes, 21),
            "vwap": vwap,
            "atr": atr,
        }
    except Exception as e:
        logging.error(f"Failed to calculate indicators: {e}")
        return None


# --- MAIN ASYNC STREAM & EVENT LOOP ---
async def main():
    book = BinanceLocalOrderBook()
    client = BinanceNetworkClient(API_KEY, SECRET_KEY)
    engine = BinanceExecutionEngine(client, book)

    async with aiohttp.ClientSession() as session:
        # Step 1: Initialize baseline state via REST snapshot
        snapshot = await client.get_depth_snapshot(session, SYMBOL_REST)
        book.apply_snapshot(snapshot)
        logging.info("Initialized REST Order Book depth snapshot.")

        # Step 2: Persistent WebSocket Loop with Auto-Reconnect
        reconnect_delay = 1
        last_indicator_update = 0
        last_heartbeat_log = 0
        cached_indicators = None

        while True:
            try:
                logging.info("Connecting to Binance WebSocket...")
                async with websockets.connect(
                    WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                ) as ws:
                    logging.info("WebSocket connected successfully.")
                    reconnect_delay = 1  # Reset backoff on successful connection

                    while True:
                        message = await ws.recv()
                        data = json.loads(message)

                        # Parse WebSocket depth updates
                        bids = data.get("bids") or data.get("b")
                        asks = data.get("asks") or data.get("a")
     
                        if bids and asks:
                            book.update_depth(bids, asks)

                        now = time.time()

                        # --- 30-SECOND HEARTBEAT LOG ---
                        if now - last_heartbeat_log >= 30:
                            best_bid, best_ask = book.get_top_of_book()
                            obi = book.get_order_book_imbalance()

                            if best_bid and best_ask:
                                spread = round(best_ask - best_bid, 2)
                                logging.info(
                                    f"[HEARTBEAT] Bot Active | Best Bid: ${best_bid:.2f} | "
                                    f"Best Ask: ${best_ask:.2f} | Spread: ${spread:.2f} | OBI: {obi:.2f}"
                                )
                            last_heartbeat_log = now

                        # Refresh Kline indicators every 15 seconds
                        if now - last_indicator_update >= 15:
                            cached_indicators = await compute_indicators(
                                client, session
                            )
                            last_indicator_update = now

                        # Evaluate market signals on each tick
                        if cached_indicators:
                            await engine.evaluate_market_signals(
                                session, cached_indicators
                            )

            except (
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
            ) as e:
                logging.warning(
                    f"WebSocket disconnected ({e}). Reconnecting in {reconnect_delay}s..."
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)

                # Refresh local snapshot upon reconnect to prevent stale depth
                try:
                    snapshot = await client.get_depth_snapshot(
                        session, SYMBOL_REST
                    )
                    book.apply_snapshot(snapshot)
                    logging.info(
                        "Re-initialized order book snapshot after disconnect."
                    )
                except Exception as snapshot_err:
                    logging.error(
                        f"Failed to refresh snapshot: {snapshot_err}"
                    )

            except Exception as e:
                logging.error(f"Unexpected error in event loop: {e}")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())