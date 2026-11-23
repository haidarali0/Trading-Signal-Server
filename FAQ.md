# Frequently Asked Questions

## What is Trading Signal Server?

Trading Signal Server is a **human-in-the-loop crypto analysis and signal research platform**, not an automated trading bot or a standalone AI trading algorithm. It helps you configure supported LLMs, provide them with structured market context, and evaluate their outputs—harnessing their capabilities rather than competing with them. It generates analysis and signals, with optional alerts; you review them and decide whether or how to act. It does not place trades for you.

The platform is intended primarily for **medium- and longer-timeframe research**, not latency-sensitive scalping. Market-data and model-provider requests take time, so it is not designed for second- or subsecond trade execution.

It helps with two practical challenges:

1. **Structuring market context:** It combines candles, indicators, and optional order-flow, news, and quantitative data into a consistent format for model analysis.
2. **Evaluating model outputs:** Results can vary with models, prompts, and settings. Historical backtests let you compare configurations and explore which performed better in the tested sample.

## How does a backtest work?

Each run fetches the latest K candles from Binance (400 by default); it doesn't use saved candle history. The backtest moves through those candles in order: the model sees the candles available at each point, generates a signal, and later candles are used to evaluate the result.
