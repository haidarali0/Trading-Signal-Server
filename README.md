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

### Adding GUI screenshots to the README

If you want to show the interface in GitHub, add screenshots under a folder such as `docs/images/` and reference them like this:

```md
![Dashboard UI](docs/images/dashboard.png)
```

Example folder structure:

```text
docs/
└── images/
    ├── dashboard.png
    ├── live-control.png
    └── backtest-panel.png
```

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
