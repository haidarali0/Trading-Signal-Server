# Contributing

Thanks for your interest in contributing to this project.

This guide explains how to set up the project, run it locally, make safe changes, and submit a pull request.

## Project overview

This repository contains a crypto trading signal platform that combines:

- live market data and technical indicators
- optional web/news context enrichment
- LLM-based signal generation and voting
- quant model support
- dashboard controls and local monitoring
- historical backtesting and result export

## Architecture focus for contributors

The project is built around a shared interface for runtime analysis and extension.

The most important extension points are:

- inference plugins: pluggable model backends and provider-specific execution paths
- preprocessing plugins: feature transforms and market-derived signal inputs
- prompt skills: reusable prompt instructions that augment the model behavior
- shared runtime interface: the common contract used by live analysis, backtesting, and dashboard tasks

If you are contributing new behavior, understand the shared execution flow first before changing specific modules.

A typical contributor path is:

1. decide whether the change belongs in the shared interface, an inference plugin, a preprocessor, or a skill
2. keep the extension compatible with the existing runtime contract
3. validate the behavior in both live and backtesting flows
4. ensure dashboard and CLI usage remain consistent

## Known limitations and suggested priorities

These are useful areas for contributions, roughly in priority order:

1. **Backtest data depth and quality:** backtests currently fetch a single Binance candle batch for each symbol. The default lookback is 400 candles, and the code does not paginate to build longer historical windows. This is a current implementation limit, not a claim that Binance's API has a 400-candle maximum. Improve longer-history ingestion with pagination or a documented local-data option, while respecting API limits and keeping historical windows reproducible.
2. **Web search and page extraction reliability:** web context depends on parsing search-result HTML and optionally scraping pages through external services or direct requests. Site markup, rate limits, blocked requests, and publication-date detection can make coverage inconsistent. Improve source reliability, extraction, attribution, and graceful failure behavior; do not treat scraped snippets as verified facts.
3. **Rule-based scoring and decision assumptions:** relevance ranking and some signal/preprocessing behavior use explicit heuristics. Make their assumptions visible, add focused tests and compare them against recorded outcomes before changing thresholds or presenting them as predictive.

When contributing in these areas, prioritize measurable reliability and reproducible evaluation over adding more sources, rules, or complexity.

## Development setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd server_for_trading_view
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root if it does not already exist.

Example:

```env
OPENROUTER_API_KEY=your_key_here
MODEL_NAME=qwen/qwen3-235b-a22b-2507
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TYPESAFE_API_KEY=your_typesafe_key_if_used
```

Important:
- do not commit real API keys to the repository
- keep local environment settings in your own `.env` file

## Running the project

### Live analysis

```bash
python main.py --dry-run
```

### Dashboard

```bash
python dashboard/app.py
```

Then open:

```text
http://localhost:8080
```

### Backtesting

```bash
python -m backtesting.backtest --symbols BTCUSDT
```

## Plugin and skill contribution model

### Inference plugins

Inference plugins define how a signal is generated and routed. They should expose the same general interface expected by the rest of the runtime, even when the underlying model or provider differs.

When adding or modifying a plugin:

- keep the plugin API compatible with the shared runtime interface
- do not assume all providers behave the same way
- preserve fallback behavior for unsupported features or missing API keys
- document any required prompt, skill, or preprocessor requirements

### Skills

Skills are prompt-layer enhancements that add extra guidance to model behavior. They are useful for structured prompting, domain behavior, or model-specific reasoning patterns.

When adding a skill:

- keep it additive and clear
- avoid hardcoding assumptions that break other models
- document whether it is intended for GenAI models, Jev flows, or both
- prefer compatibility with the shared plugin interface over custom one-off logic

### Shared interface guidance

The shared interface is the central contract that keeps the dashboard, CLI, backtesting, and model runners consistent.

Contributors should preserve:

- common argument handling
- shared output formatting
- consistent prompt and plugin selection patterns
- compatibility between live execution and backtesting

If a change affects multiple entry points, treat it as a shared-interface change, not just a local fix.

## Working on changes

### Branching

Create a short-lived feature branch before making changes:

```bash
git checkout -b feature/my-improvement
```

### Keep changes focused

- make small, specific changes
- avoid unrelated formatting fixes in the same PR
- keep commits easy to review

### Validate before submitting

Run the relevant tests or checks for your area before opening a pull request.

Examples:

```bash
pytest
```

If you are changing dashboard behavior, also validate the live app manually in the browser.

## Coding guidelines

- keep code readable and explicit
- follow the project’s existing naming conventions
- avoid hardcoding secrets or local-only values into tracked files
- keep output/logging concise and useful
- prefer small functions and clear responsibilities

## Pull request process

1. Ensure your branch is up to date with the main branch.
2. Run the relevant test or validation commands.
3. Describe what changed and why.
4. Include any setup or environment notes required for reviewers.
5. Submit a pull request with a clear title and summary.

## Reporting issues

When reporting a bug or unexpected behavior, include:

- project version or branch
- reproduction steps
- expected behavior
- actual behavior
- relevant logs or error output
- any environment details, especially `.env`-related settings

## Security note

Do not commit:

- API keys
- Telegram tokens
- local environment files
- generated cache or result files

## Questions

If you are unsure whether a change fits the project, open an issue or ask before starting large work.

Thank you for helping improve the project.
