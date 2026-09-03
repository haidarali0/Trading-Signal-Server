# Trading Signal Intelligence Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/LLM-OpenRouter-6A5CFF?style=for-the-badge" alt="OpenRouter" />
  <img src="https://img.shields.io/badge/Telegram-Alerts-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Alerts" />
  <img src="https://img.shields.io/badge/GUI-Dashboard-0A84FF?style=for-the-badge" alt="Dashboard" />
  <img src="https://img.shields.io/badge/Status-Active-4CAF50?style=for-the-badge" alt="Status Active" />
</p>

AI-powered crypto market analysis and signal platform with live execution, backtesting, quant modeling, and a local dashboard.

## Overview

This project combines:

- live crypto market data and indicators,
- OpenRouter-based LLM signal generation,
- multi-model voting for decision stability,
- quant forecasting support,
- web/news context enrichment,
- historical backtesting and metrics,
- a local GUI dashboard for monitoring and controls.

## Features

- Multi-symbol market analysis
- Technical indicator framework
- LLM consensus voting
- Telegram notifications
- Dry-run mode for safe testing
- Quant model support
- Web search context injection
- Backtesting with performance metrics
- Request caching and dataset export
- Local dashboard UI

## GUI / Dashboard

This project already includes a graphical interface in the `dashboard/` folder.

Run it with:

```bash
python dashboard/app.py
```

Then open:

```text
http://localhost:8080
```

The dashboard includes:

- Live Control
- Test Lab
- Settings
- ML Data Builder
- runtime logs and progress output

### Dashboard Screenshots

The repository includes screenshots of the main dashboard views:

![Live dashboard](dash_images/live.png)

![Test dashboard](dash_images/test.png)

![Configuration dashboard](dash_images/configs.png)

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Add environment variables

Create a `.env` file:

```env
OPENROUTER_API_KEY=your_key_here
MODEL_NAME=google/gemini-2.5-flash-lite-preview-09-2025
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3) Launch dashboard

```bash
python dashboard/app.py
```

### 4) Run analysis

```bash
python main.py
```

### 5) Safe validation mode

```bash
python main.py --dry-run
```

## Command-Line Workflows

All live and test workflows use `argparse`, so the same application can be configured from the command line without editing source code. See every available option with:

```bash
python main.py --help
python -m backtesting.backtest --help
```

### Live Commands

```bash
# Analyze the configured symbols
python main.py

# Analyze selected symbols and timeframe
python main.py --symbols BTCUSDT ETHUSDT --interval 4h --limit 500

# Run safely without Telegram delivery
python main.py --dry-run

# Use several LLMs for voting across iterations
python main.py --model-names openai/gpt-4o-mini google/gemini-2.5-flash --iterations 2

# Add quant analysis and web context
python main.py --quant-enabled --quant-models random_forest extra_trees --web-search-enabled
```

Useful live options include `--symbols`, `--interval`, `--limit`, `--model-names`, `--iterations`, `--prompt-files`, `--indicators`, `--higher-timeframes`, `--confidence-threshold`, `--gain-ratio-threshold`, `--dry-run`, and the `--quant-*` and `--web-search-*` options.

### Test and Backtest Commands

Backtesting evaluates historical signals without sending live alerts. It saves machine-readable results in `backtest_results/`.

```bash
# Backtest one symbol with default settings
python -m backtesting.backtest --symbols BTCUSDT

# Compare symbols, timeframe, and step size
python -m backtesting.backtest --symbols BTCUSDT ETHUSDT --interval 4h --lookback 400 --step 5

# Test multiple LLMs and quant models
python -m backtesting.backtest --symbols BTCUSDT --model-names openai/gpt-4o-mini google/gemini-2.5-flash --quant-enabled --quant-models random_forest extra_trees

# Control token usage, cost, and output location
python -m backtesting.backtest --symbols BTCUSDT --token-limit 10000 --max-cost 1.0 --output-dir backtest_results/experiment_01
```

Important backtest options include `--lookback`, `--step`, `--iterations`, `--n`, `--model-names`, `--token-limit`, `--input-token-price`, `--output-token-price`, `--max-cost`, `--output-dir`, and the `--quant-*` and `--web-search-*` options.

## Project Structure

```text
server_for_trading_view/
├── main.py
├── config.py
├── requirements.txt
├── README.md
├── cache/
├── backtesting/
├── crypto_data/
├── dashboard/
├── engine/
├── helper/
├── ml_builder/
├── prompts/
├── quant/
├── web/
├── tests/
├── backtest_results/
└── .env
```

## Main Commands

```bash
# Live analysis
python main.py

# Specific symbols
python main.py -s BTCUSDT ETHUSDT --interval 4h --limit 500

# Dry run
python main.py --dry-run

# Quant model enabled
python main.py --quant-enabled --quant-input-data indicators

# Web context enabled
python main.py --web-search-enabled --web-search-topics policy news

# Backtest
python -m backtesting.backtest -s BTCUSDT
```

## Backtesting

The project includes a historical evaluation engine that measures:

- win/loss rate
- return performance
- buy-and-hold comparison
- token cost tracking
- confidence and direction accuracy

Outputs are saved in `backtest_results/` and include summary JSON/CSV files.

## Data & Caching

The app stores structured runtime data in `cache/` for debugging and traceability:

- request payloads
- symbol snapshots
- web search output
- quant model results
- live stop state

## Configuration

Configuration is split between environment variables, defaults in `config.py`, dashboard settings, and command-line arguments.

### Private Environment Variables

Create `.env` locally. Never commit it or place real values in source code:

```env
OPENROUTER_API_KEY=your_key_here
MODEL_NAME=qwen/qwen3-235b-a22b-2507
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

`config.py` reads these values with `python-dotenv`. Trading defaults include symbols, candle limits, intervals, higher timeframes, indicators, confidence thresholds, and gain-ratio thresholds. Runtime overrides are available through `main.py` and the dashboard Settings tab.

### Comparing and Saving Results

Every backtest writes results incrementally so completed trades remain available if a long run stops early:

- `backtest_results/{SYMBOL}_results.json`: detailed trade-by-trade results, predictions, outcomes, returns, chart markers, and context.
- `backtest_results/summary.json`: aggregate win/loss, return, benchmark, token, and cost metrics.
- `backtest_results/{SYMBOL}_results.csv`: tabular output for spreadsheet or analysis workflows.

Use a separate output directory for each experiment, then compare the generated `summary.json` files:

```bash
python -m backtesting.backtest --symbols BTCUSDT --interval 1h --output-dir backtest_results/baseline
python -m backtesting.backtest --symbols BTCUSDT --interval 1h --quant-enabled --output-dir backtest_results/with_quant
```

This makes it possible to compare the same market and timeframe across prompt, model, indicator, quant, and threshold configurations without overwriting earlier results.

## Automatic Signal Collection and Labeling

Signals are collected automatically in `ml_builder/ml_data/dataset.jsonl`:

1. A live or backtest prediction is saved with its symbol, timestamp, predicted label (`up`, `down`, or `no_trade`), confidence, entry, target, stop-loss, expected time, analysis, and input features.
2. In backtesting, future candles are evaluated immediately. The record receives `outcome`, `return_pct`, `ground_truth`, and outcome timing.
3. In live mode, the signal is kept in a pending file until enough future candles are available. The application then checks whether the target or stop-loss was reached and updates the record with `auto_labeled: true`.
4. `append_record` avoids duplicate signal windows, while `list_records`, `export_records`, and `update_record` support dashboard and training workflows.

This produces labeled examples from actual signal outcomes instead of requiring labels to be entered manually.

## Parallel Quant Models

The quant engine prepares one shared feature matrix from OHLCV data, indicators, or both. With `--quant-models`, the configured model families train concurrently using a `ThreadPoolExecutor`:

```bash
python main.py --quant-enabled \
  --quant-models random_forest extra_trees gradient_boosting \
  --quant-input-data both \
  --quant-target-mode percentage_return
```

Supported regression models include `random_forest`, `extra_trees`, `gradient_boosting`, `hist_gradient_boosting`, `k_neighbors`, `ridge`, `svr`, `sgd`, and `passive_aggressive`. Direction targets can use classifiers such as `random_forest`, `extra_trees`, `gradient_boosting`, `hist_gradient_boosting`, or `logistic_regression`.

Each model is validated with walk-forward splits and reports metrics, confidence, reliability, and acceptance status. Accepted models are combined into a reliability-weighted ensemble; the best accepted model is also selected for the LLM context. The same quant configuration can be used during backtesting to compare model families fairly.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | LLM access |
| `MODEL_NAME` | Default model |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat target |

## Roadmap

### Near term
- improve prompt quality and signal consistency
- expand quant model coverage and validation metrics
- improve dashboard usability and run controls
- add more structured export options for analysis teams

### Medium term
- support additional exchanges and market data sources
- add stronger alert routing and signal history reviews
- improve ML dataset labeling and training workflows
- add deeper backtest comparison views and trade replay

### Long term
- introduce automated strategy tuning and parameter sweeps
- build more advanced portfolio and risk controls
- add real-time alerts and execution orchestration layers
- evolve the GUI into a complete trading research workstation

## Notes

- Use dry-run mode before live signal delivery.
- Review cached prompt payloads when debugging decisions.
- Keep prompt templates in `prompts/` for testing different strategies.
- The GUI is the fastest way to configure and monitor the workflow.

## License

This project is intended for research and experimentation in crypto market analysis. Use responsibly and in compliance with local laws and provider terms.
