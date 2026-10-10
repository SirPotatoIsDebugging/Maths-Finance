Hi there!
This is my collection of finance-related python projects!

Table of contents: 1. Orderbook and L2 data 2. Portfolio Optimisation 3. Backtesters 4. Black-Scholes

1. Orderbook and L2 related projects

Preface: Whats the order book?

The order book is, simply said, the details of individual offers for a stock, categorized in buy and sell orders.
The strategy I investigated with "L2 Data analysis" and "L2 data collector" is that there is a correlation between the OBI(Inbalance in the order book, signaling buy or sell pressure etc) and the actual increase/decrease of the stock price. In my backtest, I found a strong correlation between obi rising and subsequently the price rising with it.
This project is composed of 2 files. The first one, "l2 data collector" establishes a websocket stream to the binance api, which provides order book (also known as L2) data. This is then subsequently written to a csv file, for each 100 "observations" made

Then comes the 2. part of the project. This is the "L2 data analysis" file, where the data gets read and outputs following data: 
1. The order book data: Volume, Orderbook inbalance and midprice
2. The "future returns" compared to the order book inbalance
This is then put into a matplotlib graph.

 
 2. Portfolio optimisation
The main goal of my portfolio optimisation program is to maximise sharpe ratio.
The sharpe ratio is the risk adjusted return, it basically finds the best risk- to return ratio.
The program takes the past stock prices, downloaded via yfinance library, and calculates the annualized volatility of the stock.
   
