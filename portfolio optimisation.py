import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt


print("PORTFOLIO OPTIMIZATION CODED AT A CRISP 9 PM by Sir Potato")
stock_symbols = input("Enter the stock symbols separated by commas (e.g., AAPL,MSFT,GOOGL): ").split(',')
period = input("Enter the period for historical data (e.g., 1y, 6mo, 3mo): ")
capital = float(input("Enter the capital to invest: "))

df = yf.download(stock_symbols, period=period)['Close']

log_returns = np.log(df / df.shift(1)).dropna()

mean_returns = log_returns.mean()*252
cov_matrix = log_returns.cov()*252

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


init_guess = num_assets * [1.0 / num_assets]


result = minimize(
    min_func_sharpe,
    init_guess,
    method="SLSQP",
    bounds=bounds,
    constraints=constraints,
)

optimal_weights = result.x

num_simulations = 5000
results = np.zeros((3, num_simulations))

print("\n=== OPTIMAL PORTFOLIO WEIGHTS (Max Sharpe) ===")
for ticker, weight in zip(stock_symbols, optimal_weights):
    print(f"{ticker.strip().upper()}: {weight:.2%}")

print("\n=== CAPITAL ALLOCATION ===")
for ticker, weight in zip(stock_symbols, optimal_weights):
    allocation = capital * weight
    print(f"{ticker.strip().upper()}: ${allocation:.2f}")

print("Total Return: {:.2%}".format(get_portfolio_stats(optimal_weights, mean_returns, cov_matrix)[0]))
def compare_to_benchmark(benchmark_symbol, optimal_weights, capital):
    
    benchmark_data = yf.download(["SPY"], period=period)['Close']
    benchmark_returns = np.log(benchmark_data / benchmark_data.shift(1)).dropna()
    benchmark_mean_return = benchmark_returns.mean() * 252
    benchmark_volatility = benchmark_returns.std() * np.sqrt(252)
    benchmark_sharpe_ratio = (benchmark_mean_return - 0.04) / benchmark_volatility

    optimal_portfolio_return, optimal_portfolio_volatility, optimal_portfolio_sharpe = get_portfolio_stats(optimal_weights, mean_returns, cov_matrix)

    if optimal_portfolio_sharpe > benchmark_sharpe_ratio:
        print("\nThe optimal portfolio outperforms the benchmark (SPY) in terms of Sharpe Ratio. MIGHT BE ALPHA!!!")


for i in range(num_simulations):

  weights = np.random.random(num_assets)
  weights /= np.sum(weights)

  ret, vol, sharpe = get_portfolio_stats(weights, mean_returns, cov_matrix)
  results[0, i] = vol
  results[1, i] = ret
  results[2, i] = sharpe

plt.scatter(
    results[0, :], results[1, :], c=results[2, :], cmap="viridis", s=10
)
# Compute stats for the optimal weight vector
opt_ret, opt_vol, opt_sharpe = get_portfolio_stats(optimal_weights, mean_returns, cov_matrix)

# Plot the Monte Carlo cloud
plt.scatter(results[0, :], results[1, :], c=results[2, :], cmap="viridis", s=10)
plt.colorbar(label="Sharpe Ratio")

# Highlight the Max Sharpe portfolio as a red star
plt.scatter(opt_vol, opt_ret, color='red', marker='*', s=200, label=f'Max Sharpe ({opt_sharpe:.2f})')

plt.xlabel("Annualized Volatility")
plt.ylabel("Annualized Return")
plt.legend()
plt.show()
plt.colorbar(label="Sharpe Ratio")
plt.xlabel("Annualized Volatility")
plt.ylabel("Annualized Return")
plt.show()
