from datetime import datetime
import sys
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf


def stock_download(stock_name, start_date, end_date):
    df = yf.download(stock_name, start=start_date, end=end_date)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def calculate_atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()


def trading_strategy(df):
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["SMA_200"] = df["Close"].rolling(window=200).mean()
    df["ATR"] = calculate_atr(df, period=14)

    tp_vol = ((df["High"] + df["Low"] + df["Close"]) / 3) * df["Volume"]
    df["VWAP"] = tp_vol.groupby(df.index.date).cumsum() / df[
        "Volume"
    ].groupby(df.index.date).cumsum()
    return df


def backtest_no_filter(df):
    df["Position_NoFilter"] = np.where(df["EMA_20"] > df["VWAP"], 1, 0)
    df["Returns_NoFilter"] = (
        df["Close"].pct_change() * df["Position_NoFilter"].shift(1)
    )
    df["Cum_NoFilter"] = (1 + df["Returns_NoFilter"].fillna(0)).cumprod()
    return df


def backtest_200sma_fixed_sl(df, stop_loss_pct=0.02):
    n = len(df)
    positions = np.zeros(n)
    entry_price = 0.0
    in_position = False

    close = df["Close"].values
    ema = df["EMA_20"].values
    vwap = df["VWAP"].values
    sma200 = df["SMA_200"].values

    for i in range(1, n):
        current_close = close[i]

        if in_position:
            loss = (current_close - entry_price) / entry_price
            if loss <= -stop_loss_pct:
                in_position = False
                positions[i] = 0
                continue

        buy_signal = (ema[i] > vwap[i]) and (
            not np.isnan(sma200[i]) and current_close > sma200[i]
        )
        exit_signal = ema[i] <= vwap[i]

        if buy_signal and not in_position:
            in_position = True
            entry_price = current_close
            positions[i] = 1
        elif exit_signal and in_position:
            in_position = False
            positions[i] = 0
        elif in_position:
            positions[i] = 1

    df["Returns_200SMA"] = (
        df["Close"].pct_change() * pd.Series(positions, index=df.index).shift(1)
    )
    df["Cum_200SMA"] = (1 + df["Returns_200SMA"].fillna(0)).cumprod()
    return df


def backtest_atr_trailing_sl(df, atr_multiplier=3.0):
    n = len(df)
    positions = np.zeros(n)
    trailing_stop = 0.0
    in_position = False

    close = df["Close"].values
    ema20 = df["EMA_20"].values
    ema50 = df["EMA_50"].values
    vwap = df["VWAP"].values
    atr = df["ATR"].values

    for i in range(1, n):
        current_close = close[i]

        if in_position:
            if current_close < trailing_stop:
                in_position = False
                positions[i] = 0
                continue
            else:
                trailing_stop = max(
                    trailing_stop, current_close - (atr[i] * atr_multiplier)
                )

        buy_signal = (
            (ema20[i] > vwap[i])
            and (not np.isnan(ema50[i]) and current_close > ema50[i])
            and not np.isnan(atr[i])
        )
        exit_signal = ema20[i] <= vwap[i]

        if buy_signal and not in_position:
            in_position = True
            trailing_stop = current_close - (atr[i] * atr_multiplier)
            positions[i] = 1
        elif exit_signal and in_position:
            in_position = False
            positions[i] = 0
        elif in_position:
            positions[i] = 1

    df["Returns_ATR"] = (
        df["Close"].pct_change() * pd.Series(positions, index=df.index).shift(1)
    )
    df["Cum_ATR"] = (1 + df["Returns_ATR"].fillna(0)).cumprod()
    return df


def calculate_metrics(returns, cum_returns):
    returns = returns.dropna()
    if len(returns) == 0 or returns.std() == 0:
        return 0.0, 0.0

    sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()

    return sharpe_ratio, max_drawdown


def results(df):
    market_returns = (1 + df["Close"].pct_change().fillna(0)).cumprod()

    sharpe_mkt, mdd_mkt = calculate_metrics(
        df["Close"].pct_change(), market_returns
    )
    sharpe_no_filter, mdd_no_filter = calculate_metrics(
        df["Returns_NoFilter"], df["Cum_NoFilter"]
    )
    sharpe_200sma, mdd_200sma = calculate_metrics(
        df["Returns_200SMA"], df["Cum_200SMA"]
    )
    sharpe_atr, mdd_atr = calculate_metrics(
        df["Returns_ATR"], df["Cum_ATR"]
    )

    template = "{:<16} | {:>12} | {:>12} | {:>16} | {:>16}\n"

    out = "\n" + "=" * 82 + "\n"
    out += template.format(
        "Metric", "Buy & Hold", "No Filter", "200 SMA + 2% SL", "ATR Trailing"
    )
    out += "=" * 82 + "\n"
    out += template.format(
        "Total Return",
        f"{market_returns.iloc[-1]-1:.2%}",
        f"{df['Cum_NoFilter'].iloc[-1]-1:.2%}",
        f"{df['Cum_200SMA'].iloc[-1]-1:.2%}",
        f"{df['Cum_ATR'].iloc[-1]-1:.2%}",
    )
    out += template.format(
        "Sharpe Ratio",
        f"{sharpe_mkt:.2f}",
        f"{sharpe_no_filter:.2f}",
        f"{sharpe_200sma:.2f}",
        f"{sharpe_atr:.2f}",
    )
    out += template.format(
        "Max Drawdown",
        f"{mdd_mkt:.2%}",
        f"{mdd_no_filter:.2%}",
        f"{mdd_200sma:.2%}",
        f"{mdd_atr:.2%}",
    )
    out += "=" * 82 + "\n"

    sys.stdout.write(out)
    sys.stdout.flush()


def plot_combined_graph(df, stock):
    plt.figure(figsize=(14, 7))
    market_returns = (1 + df["Close"].pct_change().fillna(0)).cumprod()

    plt.plot(
        df.index,
        market_returns,
        label="Buy & Hold (Market)",
        color="gray",
        linestyle="--",
        alpha=0.7,
    )
    plt.plot(
        df.index,
        df["Cum_NoFilter"],
        label="No Filter (Pure EMA/VWAP)",
        color="orange",
        linewidth=1.5,
    )
    plt.plot(
        df.index,
        df["Cum_200SMA"],
        label="200 SMA + 2% Fixed Stop-Loss",
        color="crimson",
        linewidth=1.5,
    )
    plt.plot(
        df.index,
        df["Cum_ATR"],
        label="ATR Trailing Stop + 50 EMA Filter",
        color="limegreen",
        linewidth=2.0,
    )

    plt.title(f"Strategy Comparison Benchmark: {stock}")
    plt.xlabel("Date")
    plt.ylabel("Growth of $1")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show(block=True)


def main():
    stock_name = input("Enter the stock ticker (e.g., AAPL): ").upper().strip()
    start_date = input("Enter the start date (YYYY-MM-DD): ").strip()
    end_date = datetime.now().strftime("%Y-%m-%d")

    data = stock_download(stock_name, start_date, end_date)
    data = trading_strategy(data)
    
    # ALL THREE BACKTESTS ARE CALLED HERE:
    data = backtest_no_filter(data)
    data = backtest_200sma_fixed_sl(data, stop_loss_pct=0.02)
    data = backtest_atr_trailing_sl(data, atr_multiplier=3.0)

    results(data)
    plot_combined_graph(data, stock_name)


if __name__ == "__main__":
    main()