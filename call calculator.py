import math
import numpy as np
import pandas as pd
import scipy
import yfinance as yf
from datetime import datetime

print("--- Black-Scholes Option/Call & Greeks Calculator ---")
ticker_symbol = input("Which stock ticker? (e.g., AAPL): ").upper()
type_of_option = input("Which type of option? (call/put): ").lower()

stock_history = yf.download(ticker_symbol, period="1y")
closing_price = stock_history["Close"]

log_returns = np.log(closing_price / closing_price.shift(1))

sigma = float(log_returns.std() * np.sqrt(252))
if np.isnan(sigma) or sigma <= 0:
    raise ValueError("Calculated volatility is invalid. Please check the stock ticker and data availability.")
print(f"Calculated 1-Year Volatility (sigma): {sigma:.4f}")

N = scipy.stats.norm.cdf


def d1_formula(S, K, T, r, sigma):
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def call_price(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return S * N(d1) - K * math.exp(-r * T) * N(d2)


def put_price(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * N(-d2) - S * N(-d1)


def phi(x):
    return scipy.stats.norm.pdf(x)


def call_delta(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    return N(d1)


def put_delta(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    return N(d1) - 1


def call_gamma(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    return phi(d1) / (S * sigma * math.sqrt(T))


def put_gamma(S, K, T, r, sigma):
    return call_gamma(S, K, T, r, sigma)


def call_theta(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return -(S * phi(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * N(d2)


def put_theta(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return -(S * phi(d1) * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * N(-d2)


def call_vega(S, K, T, r, sigma):
    d1 = d1_formula(S, K, T, r, sigma)
    return S * phi(d1) * math.sqrt(T)


def put_vega(S, K, T, r, sigma):
    return call_vega(S, K, T, r, sigma)


def call_rho(S, K, T, r, sigma):
    d2 = d1_formula(S, K, T, r, sigma) - sigma * math.sqrt(T)
    return K * T * math.exp(-r * T) * N(d2)


def put_rho(S, K, T, r, sigma):
    d2 = d1_formula(S, K, T, r, sigma) - sigma * math.sqrt(T)
    return -K * T * math.exp(-r * T) * N(-d2)


def get_params():
    global S, K, T, r, C_market
    ticker = yf.Ticker(ticker_symbol)
    S = float(ticker.history(period="1d")["Close"].iloc[0])
    expirations = ticker.options
    if not expirations:
        raise ValueError(f"No option expirations available for {ticker_symbol}.")

    target_date = expirations[0]
    opt_chain = ticker.option_chain(target_date)
    if type_of_option == "call":
        chain = opt_chain.calls
    elif type_of_option == "put":
        chain = opt_chain.puts
    else:
        raise ValueError("Option type must be 'call' or 'put'.")

    if chain.empty:
        raise ValueError(f"No {type_of_option} options available for {ticker_symbol} on {target_date}.")

    last_price = float(ticker.fast_info["lastPrice"])
    atm_option = chain.iloc[(chain["strike"] - last_price).abs().idxmin()]

    K = float(atm_option["strike"])
    C_market = float(atm_option["lastPrice"])

    exp_date = datetime.strptime(target_date, "%Y-%m-%d")
    today = datetime.now()
    T = max((exp_date - today).days / 365.0, 1e-5)

    r = float(input("Enter the risk-free interest rate (as a decimal, e.g., 0.05 for 5%): "))


def price_difference_for_option(sigma, option_type, S, K, T, r, market_price):
    if option_type == "call":
        return call_price(S, K, T, r, sigma) - market_price
    if option_type == "put":
        return put_price(S, K, T, r, sigma) - market_price
    raise ValueError("Option type must be 'call' or 'put'.")


def iv_brent(C_market, S, K, T, r, option_type="call", tol=1e-6, max_iter=100):
    def price_difference(sigma):
        return price_difference_for_option(sigma, option_type, S, K, T, r, C_market)

    low_sigma = 1e-9
    high_sigma = 1.0
    low_value = price_difference(low_sigma)
    high_value = price_difference(high_sigma)
    while high_value < 0 and high_sigma < 10.0:
        high_sigma *= 2.0
        high_value = price_difference(high_sigma)

    if low_value * high_value > 0:
        raise ValueError("Could not bracket the implied volatility.")

    return scipy.optimize.brentq(
        price_difference, low_sigma, high_sigma, xtol=tol, maxiter=max_iter
    )


get_params()

if type_of_option == "call":
    print("\n--- Results ---")
    print(f"Call Option Price: ${call_price(S, K, T, r, sigma):.2f}")
    print(f"Implied Volatility (IV) using Brent's method: {iv_brent(C_market, S, K, T, r, option_type='call'):.4f}")
    print(f"Greeks: Delta={call_delta(S, K, T, r, sigma):.4f}, Gamma={call_gamma(S, K, T, r, sigma):.4f}, Theta={call_theta(S, K, T, r, sigma):.4f}, Vega={call_vega(S, K, T, r, sigma):.4f}, Rho={call_rho(S, K, T, r, sigma):.4f} ")

elif type_of_option == "put":
    print("\n--- Results ---")
    print(f"Put Option Price: ${put_price(S, K, T, r, sigma):.2f}")
    print(f"Implied Volatility (IV) using Brent's method: {iv_brent(C_market, S, K, T, r, option_type='put'):.4f}")
    print(f"Greeks: Delta={put_delta(S, K, T, r, sigma):.4f}, Gamma={put_gamma(S, K, T, r, sigma):.4f}, Theta={put_theta(S, K, T, r, sigma):.4f}, Vega={put_vega(S, K, T, r, sigma):.4f}, Rho={put_rho(S, K, T, r, sigma):.4f} ")

def put_call_parity(S, K, T, r, C_market):
    return C_market + K * math.exp(-r * T) - S


if type_of_option == "call":
    print(f"Put Price from Put-Call Parity: ${put_call_parity(S, K, T, r, C_market):.2f}")


def iv_smile():
    ticker_obj = yf.Ticker(ticker_symbol)
    expirations = ticker_obj.options
    if not expirations:
        raise ValueError(f"No option expirations available for {ticker_symbol}.")

    target_date = expirations[0]
    option_chain = ticker_obj.option_chain(target_date)
    chain = option_chain.calls if type_of_option == "call" else option_chain.puts

    smile_data = []
    for _, option in chain.iterrows():
        K = float(option["strike"])
        bid = float(option["bid"])
        ask = float(option["ask"])

        if bid <= 0 or ask < bid:
            continue

        market_price = (bid + ask) / 2

        try:
            iv = iv_brent(
                market_price,
                S,
                K,
                T,
                r,
                option_type=type_of_option,
            )
            smile_data.append({"strike": K, "iv": iv})
        except ValueError:
            pass

    return pd.DataFrame(smile_data)


smile_df = iv_smile()
if not smile_df.empty:
    import matplotlib.pyplot as plt

    plt.plot(smile_df["strike"], smile_df["iv"], marker="o")
    plt.xlabel("Strike")
    plt.ylabel("Implied Volatility")
    plt.title(f"{ticker_symbol} IV Smile")
    plt.show()
else:
    print("No valid option prices were found to plot the IV smile.")

