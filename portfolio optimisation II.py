#portfolio optimsation II, moving away from log-returns
import math

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt


print("PORTFOLIO OPTIMIZATION CODED AT A CRISP 9 PM by Sir Potato")
stock_symbols = input("Enter the stock symbols separated by commas (e.g., AAPL,MSFT,GOOGL): ").split(',')
period = input("Enter the period for historical data (e.g., 1y, 6mo, 3mo): ")
capital = float(input("Enter the capital to invest: "))
lambda_val = float(input("Enter the lambda value for EWMA (e.g., 0.94): "))
df = yf.download(stock_symbols, period=period)['Close']


def portfolio_control():
    log_returns = np.log(df / df.shift(1)).dropna()

    mean_returns = log_returns.mean() * 252
    cov_matrix = log_returns.cov() * 252

    def get_portfolio_stats(weights, mean_returns, cov_matrix, risk_free_rate=0.04):
        p_returns = np.sum(mean_returns * weights)
        p_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe_ratio = (p_returns - risk_free_rate) / p_volatility
        return p_returns, p_volatility, sharpe_ratio

    from scipy.optimize import minimize

    num_assets = len(mean_returns)

    def min_func_sharpe(weights):
        _, _, sharpe = get_portfolio_stats(weights, mean_returns, cov_matrix)
        return -sharpe

    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    bounds = tuple((0.0, 1.0) for _ in range(num_assets))
    init_guess = [1.0 / num_assets for _ in range(num_assets)]

    result = minimize(
        min_func_sharpe,
        init_guess,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        raise RuntimeError(result.message)

    optimal_weights = result.x

    print("\n=== OPTIMAL PORTFOLIO WEIGHTS (Max Sharpe) ===")
    for ticker, weight in zip(stock_symbols, optimal_weights):
        print(f"{ticker.strip().upper()}: {weight:.2%}")

    print("\n=== CAPITAL ALLOCATION ===")
    for ticker, weight in zip(stock_symbols, optimal_weights):
        allocation = capital * weight
        print(f"{ticker.strip().upper()}: ${allocation:.2f}")

    print(f"Total Return: {get_portfolio_stats(optimal_weights, mean_returns, cov_matrix)[0]:.2%}")
    return optimal_weights, mean_returns, cov_matrix


optimal_weights, mean_returns, cov_matrix = portfolio_control()


print("EMWA Covariance Matrix Calculation")

def ewma_matrix(ewma_lambda):
    ewma_cov_matrix = (
        df.pct_change()
        .ewm(alpha=1 - ewma_lambda, ignore_na=True)
        .cov()
        .iloc[-len(df.columns):]
    )
    return ewma_cov_matrix


def portfolio_sigma_emwa(weights, ewma_lambda):
    ewma_cov = ewma_matrix(ewma_lambda)
    sigma_t = np.sqrt(np.dot(weights.T, np.dot(ewma_cov, weights)))*math.sqrt(252)  # Annualize the volatility
    return sigma_t


sigma_historical = np.sqrt(np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights)))
sigma_ewma = portfolio_sigma_emwa(optimal_weights, ewma_lambda=lambda_val)
if __name__ == "__main__":
    print(f"\nHistorical Portfolio Volatility: {sigma_historical:.4%}")
    print(f"EWMA Portfolio Volatility (lambda={lambda_val}): {sigma_ewma:.4%}")