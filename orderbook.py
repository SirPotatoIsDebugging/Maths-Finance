import random
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf


class OrderBook:

    def __init__(self):
    # Lists to store active bids (buyers) and asks (sellers)
        self.bids = []
        self.asks = []

    def add_order(self, side, price, qty):
        if side == "buy":
            self._match_buy(price, qty)
        elif side == "sell":
            self._match_sell(price, qty)

    def _match_buy(self, price, qty):
    # Match against lowest asks first
        while self.asks and qty > 0 and price >= self.asks[0]["price"]:
            best_ask = self.asks[0]
            if qty >= best_ask["qty"]:
                qty -= best_ask["qty"]
                self.asks.pop(0)
            else:
                best_ask["qty"] -= qty
                qty = 0
        if qty > 0:
            self.bids.append({"price": price, "qty": qty})
        self.bids.sort(key=lambda x: x["price"], reverse=True)

    def _match_sell(self, price, qty):
    # Match against highest bids first
        while self.bids and qty > 0 and price <= self.bids[0]["price"]:
            best_bid = self.bids[0]
            if qty >= best_bid["qty"]:
                qty -= best_bid["qty"]
                self.bids.pop(0)
            else:
                best_bid["qty"] -= qty
                qty = 0
        if qty > 0:
            self.asks.append({"price": price, "qty": qty})
        self.asks.sort(key=lambda x: x["price"])

# --- 1. Initialize Simulation & Fetch Baseline ---
book = OrderBook()
ticker_symbol = "MSFT"
stock_data = yf.download(ticker_symbol, period="1d")
if stock_data.empty:
    raise RuntimeError(f"Could not download price data for {ticker_symbol}")

# yfinance may return a Series or a one-column DataFrame for Close,
# depending on whether the result has a single-level or MultiIndex column.
close_data = stock_data["Close"]
baseline_price = float(close_data.iloc[-1].squeeze())

print(f"Simulating market around {ticker_symbol} baseline: ${baseline_price:.2f}")

market_history = []

# --- 2. Run Simulation Loop & Log Metrics ---
# We simulate 50 time steps of random order flow
for step in range(50):
  # Randomly add buy and sell orders around the baseline
  buy_spread = random.uniform(0.001, 0.015)
  sell_spread = random.uniform(0.001, 0.015)

  book.add_order(
      "buy",
      round(baseline_price * (1 - buy_spread), 2),
      random.randint(1, 10) * 10,
  )
  book.add_order(
      "sell",
      round(baseline_price * (1 + sell_spread), 2),
      random.randint(1, 10) * 10,
  )

  # Occasionally inject a market order to clear liquidity
  if step % 5 == 0 and book.asks:
    book.add_order("buy", book.asks[0]["price"], 15)

  # Log the state if both books have active orders
  if book.bids and book.asks:
    best_bid = book.bids[0]["price"]
    best_ask = book.asks[0]["price"]
    spread = round(best_ask - best_bid, 4)
    ofi = book.bids[0]["qty"] - book.asks[0]["qty"]

    market_history.append(
        {"Step": step, "Spread": spread, "OFI": ofi, "Best_Bid": best_bid}
    )


# Convert log to a Pandas DataFrame
df_market = pd.DataFrame(market_history)

# --- 3. Plotting with Matplotlib ---

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

# Top Subplot: Bid-Ask Spread
ax1.plot(
    df_market["Step"],
    df_market["Spread"],
    color="#1f77b4",
    linewidth=2,
    marker="o",
    markersize=3,
)
ax1.set_ylabel("Bid-Ask Spread ($)")
ax1.set_title(f"Local Order Book Simulation Analytics ({ticker_symbol})")
ax1.grid(True, linestyle="--", alpha=0.6)

# Bottom Subplot: Order Flow Imbalance (OFI)
ax2.plot(
    df_market["Step"],
    df_market["OFI"],
    color="#ff7f0e",
    linewidth=2,
    marker="s",
    markersize=3,
)
ax2.axhline(0, color="black", linestyle="--", linewidth=1)
ax2.set_ylabel("Order Flow Imbalance")
ax2.set_xlabel("Simulation Step")
ax2.grid(True, linestyle="--", alpha=0.6)

plt.tight_layout()
plt.show()


avg_obi = df_market["OFI"].mean()
avg_spread = df_market["Spread"].mean()
print(f"Average Order Flow Imbalance (OFI): {avg_obi:.2f}")
print(f"Average Bid-Ask Spread: {avg_spread:.4f}")
   