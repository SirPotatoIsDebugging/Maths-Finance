import yfinance as yf
import pandas as pd

df=yf.download("MSFT", period="1y")
df["SMA_50"]= df["Close"].rolling(window=50).mean()
df["SMA_200"]= df["Close"].rolling(window=200).mean()
df["Signal"]=0
df.loc[df["SMA_50"]>df["SMA_200"], "Signal" ]=1

# 4. Calculate strategy returns vs. buy-and-hold
df["Market_Returns"] = df["Close"].pct_change()
df["Strategy_Returns"] = df["Market_Returns"] * df["Signal"].shift(1)

# 5. Print final performance comparison
print("Total Market Return:", (1 + df["Market_Returns"].dropna()).prod() - 1)
print(
    "Total Strategy Return:", (1 + df["Strategy_Returns"].dropna()).prod() - 1
)
