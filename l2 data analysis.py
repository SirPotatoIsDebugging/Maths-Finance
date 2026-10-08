import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pathlib import Path


def user_data():
    DATA_DIR = Path("data/crypto")

    files = sorted(DATA_DIR.glob("*.csv"))

    if not files:
        raise FileNotFoundError("No datasets found.")

    print("\n--- Available datasets ---")

    for i, file in enumerate(files, start=1):
        print(f"{i}. {file.name}")

    choice = int(input("\nChoose dataset: "))

    if choice < 1 or choice > len(files):
        raise ValueError("Invalid selection.")

    data_file = files[choice - 1]

    print(f"\nLoading: {data_file}")
    return data_file


def load_data(data_file):
    df = pd.read_csv(data_file)
    df["received_time"] = pd.to_datetime(
        df["received_time"],
        unit="s",
        utc=True
    )
    return df


def timestamps(df):
    df["timedelta"] = (
        df["received_time"]
        .diff()
        .dt.total_seconds()
    )
    return df

def timestamp_metrics(df):
    timedeltas = df["timedelta"].dropna()
    return {
        "min": timedeltas.min(),
        "max": timedeltas.max(),
        "mean": timedeltas.mean(),
        "median": timedeltas.median(),
        "standard_deviation": timedeltas.std(),
        "zero_intervals": int(timedeltas.eq(0).sum()),
    }



def get_metrics(df):
    metrics = {
        "Mid Price": df["midprice"],
        "Order Book Imbalance": df["obi"],
        "Spread": df["spread"].round(5)
    }

    return metrics
def timestamp_match(df, offset_seconds=1):

    if "received_time" not in df.columns or "midprice" not in df.columns:
        raise KeyError(
            "DataFrame must contain 'received_time' and 'midprice' columns."
        )

    prices_by_time = df.set_index("received_time")["midprice"]

    target_times = (
        df["received_time"]
        + pd.to_timedelta(offset_seconds, unit="s")
    )

    def find_closest(ts):
        deltas = (prices_by_time.index - ts).asi8
        return prices_by_time.index[np.abs(deltas).argmin()]

    future_times = target_times.apply(find_closest)

    future_midprices = future_times.map(prices_by_time)

    future_returns = (
        future_midprices - df["midprice"]
    ) / df["midprice"]

    return future_returns

def group_obi_ranges(df, bins):
    if "obi" not in df.columns:
        raise KeyError("DataFrame must contain 'obi' column.")

    df["obi_range"] = pd.cut(df["obi"], bins=bins)

    grouped = (
        df.groupby("obi_range")["future_returns"]
        .agg(["mean", "count"])
        .reset_index()
    )

    return grouped
def print_count_from_grouped(grouped):
    print("\n--- Count of Observations by OBI Range ---")
    for _, row in grouped.iterrows():
        print(
            f"OBI Range: {row['obi_range']}, "
            f"Count: {row['count']}"
        )

def calculate_correlation(df):
    if "obi" not in df.columns or "future_returns" not in df.columns:
        raise KeyError(
            "DataFrame must contain 'obi' and 'future_returns' columns."
        )

    correlation = df["obi"].corr(df["future_returns"])
    return correlation
def plot_metrics(df, metrics):

    _, axes = plt.subplots(
        3,
        1,
        figsize=(12, 10),
        sharex=True
    )

    # Mid price
    axes[0].plot(
        df["received_time"],
        metrics["Mid Price"]
    )
    axes[0].set_ylabel("Mid Price")
    axes[0].set_title("Mid Price Over Time")
    axes[0].grid(True)

    # OBI
    axes[1].plot(
        df["received_time"],
        metrics["Order Book Imbalance"]
    )
    axes[1].set_ylabel("OBI")
    axes[1].set_title("Order Book Imbalance Over Time")
    axes[1].grid(True)

    # Spread
    axes[2].plot(
        df["received_time"],
        metrics["Spread"]
    )
    axes[2].set_ylabel("Spread")
    axes[2].set_xlabel("Time")
    axes[2].set_title("Spread Over Time")
    axes[2].grid(True)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def plot_obi_vs_future_returns(grouped):

    plt.figure(figsize=(10, 6))

    plt.plot(
        grouped["obi_range"].astype(str),
        grouped["mean"],
        marker="o"
    )

    plt.axhline(0, linewidth=1)

    plt.xlabel("OBI Range")
    plt.ylabel("Mean 1-Second Future Return")
    plt.title("OBI vs Mean 1-Second Future Return")
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    data_file = user_data()
    df = load_data(data_file)
    df = timestamps(df)
    df["future_returns"] = timestamp_match(df)
    metrics = get_metrics(df)
    plot_metrics(df, metrics)
    plot_obi_vs_future_returns(
        group_obi_ranges(df, bins=10)
    )
    print_count_from_grouped(
        group_obi_ranges(df, bins=10))
    print(f"Correlation between OBI and Future Returns: {calculate_correlation(df):.4f}")



    