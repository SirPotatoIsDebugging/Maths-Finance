import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


os.environ.pop("SSLKEYLOGFILE", None)

import aiohttp
import pandas as pd




SYMBOL = input("Trading pair (e.g. SOLUSDT): ").strip().upper()
SYMBOL_WS = SYMBOL.lower()

DATA_DIR = Path("data") / "crypto"

BATCH_SIZE = 100
RECONNECT_DELAY = 5

STREAM_URL = (
    f"wss://stream.binance.com:9443/ws/"
    f"{SYMBOL_WS}@depth10@100ms"
)


def get_data_file(received_time):
    date = datetime.fromtimestamp(
        received_time,
        timezone.utc
    ).strftime("%Y-%m-%d")

    return DATA_DIR / f"{SYMBOL}_{date}.csv"


def save_batch(batch):
    if not batch:
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(batch)

    # A batch could technically cross midnight,
    # so split it by UTC date before saving.
    dates = pd.to_datetime(
        df["received_time"],
        unit="s",
        utc=True
    ).dt.strftime("%Y-%m-%d")

    df["date"] = dates

    for date, date_df in df.groupby("date"):

        data_file = DATA_DIR / f"{SYMBOL}_{date}.csv"

        file_exists = data_file.exists()

        date_df = date_df.drop(columns=["date"])

        date_df.to_csv(
            data_file,
            mode="a",
            header=not file_exists,
            index=False
        )

        print(
            f"Saved {len(date_df)} observations "
            f"to {data_file}"
        )



def create_observation(data):

    bids = data.get("bids", [])
    asks = data.get("asks", [])

    if not bids or not asks:
        return None

    observation = {
        "received_time": time.time(),
        "update_id": data.get("lastUpdateId"),
    }



    for level in range(10):

        # Bid
        if level < len(bids):
            observation[f"bid_{level + 1}_price"] = float(
                bids[level][0]
            )
            observation[f"bid_{level + 1}_qty"] = float(
                bids[level][1]
            )
        else:
            observation[f"bid_{level + 1}_price"] = None
            observation[f"bid_{level + 1}_qty"] = None

        # Ask
        if level < len(asks):
            observation[f"ask_{level + 1}_price"] = float(
                asks[level][0]
            )
            observation[f"ask_{level + 1}_qty"] = float(
                asks[level][1]
            )
        else:
            observation[f"ask_{level + 1}_price"] = None
            observation[f"ask_{level + 1}_qty"] = None



    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])

    observation["best_bid"] = best_bid
    observation["best_ask"] = best_ask

    
    observation["midprice"] = (
        best_bid + best_ask
    ) / 2

   
    observation["spread"] = (
        best_ask - best_bid
    )



    total_bid_qty = sum(
        float(level[1])
        for level in bids
    )

    total_ask_qty = sum(
        float(level[1])
        for level in asks
    )

    observation["total_bid_qty"] = total_bid_qty
    observation["total_ask_qty"] = total_ask_qty



    total_qty = (
        total_bid_qty + total_ask_qty
    )

    if total_qty > 0:
        observation["obi"] = (
            (total_bid_qty - total_ask_qty)
            / total_qty
        )
    else:
        observation["obi"] = 0.0

    return observation




async def collect():

    batch = []

    while True:

        try:

            print(
                f"\nConnecting to {STREAM_URL}"
            )

            async with aiohttp.ClientSession() as session:

                async with session.ws_connect(
                    STREAM_URL,
                    heartbeat=20,
                    autoping=True,
                ) as ws:

                    print(
                        f"Connected. Collecting "
                        f"{SYMBOL} L2 data..."
                    )

                    async for message in ws:

                        if message.type == aiohttp.WSMsgType.TEXT:

                            data = json.loads(
                                message.data
                            )

                            observation = (
                                create_observation(data)
                            )

                            if observation is None:
                                continue

                            batch.append(
                                observation
                            )

                            if len(batch) >= BATCH_SIZE:
                                save_batch(batch)
                                batch.clear()

                        elif message.type == aiohttp.WSMsgType.ERROR:

                            print(
                                f"WebSocket error: "
                                f"{ws.exception()}"
                            )

                            break

                        elif message.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                        ):

                            print(
                                "WebSocket closed."
                            )

                            break

        except KeyboardInterrupt:
            raise

        except Exception as error:

            print(
                f"Collector error: {error}"
            )


        if batch:
            try:
                save_batch(batch)
                batch.clear()
            except Exception as error:
                print(
                    f"Could not save buffered "
                    f"observations: {error}"
                )

        print(
            f"Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )

        await asyncio.sleep(
            RECONNECT_DELAY
        )




if __name__ == "__main__":

    try:
        asyncio.run(collect())

    except KeyboardInterrupt:
        print("\nCollector stopped.")