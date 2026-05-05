# Trading Signal Server

A Python-based trading signal system that uses LLM-driven market analysis and sends alerts via Telegram.

This project is built to:
- connect directly to Telegram for automated signal delivery,
- fetch free technical indicators from market data APIs,
- support OpenRouter so you can choose any available LLM model easily,
- analyze multiple symbols with flexible timeframe and indicator settings,
- output charts and signal summaries for each analysis run,
- provide backtesting capabilities with token usage and cost tracking,
- run in dry-run mode when you want to test without sending Telegram messages.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the root directory with your API keys:
   ```
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   MODEL_NAME=google/gemini-2.5-flash-lite-preview-09-2025
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   TELEGRAM_CHAT_ID=your_telegram_chat_id_here
   ```

## Configuration

Default settings can be modified in `config.py`:
- Trading symbols
- Timeframes
- Analysis parameters
- Confidence thresholds

## Usage

Run the main analysis with default settings:
```bash
python main.py
```

### Command Line Options

The system supports various command-line arguments for customization:

```bash
python main.py [OPTIONS]
```

#### Options:
- `-s, --symbols SYMBOLS`: Symbols to analyze (default: BTCUSDT, BNBUSDT, ZECUSDT, ETHUSDT, PEPEUSDT, XRPUSDT, DOGEUSDT, SOLUSDT, FUNUSDT, ASTRUSDT, ETHFIUSDT)
- `--interval INTERVAL`: Main timeframe interval (default: 1h)
- `--limit LIMIT`: Number of candles to fetch (default: 400)
- `--higher-timeframes TF`: Higher timeframe intervals (default: 4h)
- `--confidence-threshold THRESH`: Minimum confidence for signals (default: 0.7)
- `--gain-ratio-threshold THRESH`: Minimum gain ratio (default: 1.0)
- `--indicators INDICATORS`: Indicator columns to include (default: EMA20 EMA50 EMA100 EMA200 sma20 sma50 rsi macd_line macd_signal macd_hist stoch_k stoch_d atr bb_upper bb_middle bb_lower vwap)
- `--iterations N`: Number of analysis iterations per symbol (default: 2)
- `--dry-run`: Run analysis without sending Telegram messages

#### Examples:
```bash
# Analyze specific symbols
python main.py -s BTCUSDT ETHUSDT

# Use a smaller indicator set
python main.py --indicators EMA20 EMA50 rsi

# Custom timeframe and data limit
python main.py --interval 4h --limit 500

# Test without sending messages
python main.py --dry-run

# Multiple symbols with custom settings
python main.py -s BTCUSDT ETHUSDT --interval 1h --confidence-threshold 0.8
```

## Backtesting

The system includes a backtesting module to evaluate performance on historical data.

### Usage

Run backtesting with recent candles and optional token cost controls:
```bash
python -m backtesting.backtest -s BTCUSDT
```

#### Backtesting Options:
- `-s, --symbols SYMBOLS`: Symbols to backtest (default: first 2 symbols from config, e.g. BTCUSDT BNBUSDT)
- `--lookback N`: Number of most recent candles to load (default: 400)
- `--interval INTERVAL`: Timeframe interval (default: 1h)
- `--step STEP`: Step size in candles between tests (default: 10)
- `--n N`: Number of recent candles used for LLM input (default: 40)
- `--higher-timeframes TF`: Higher timeframe intervals (default: [4h])
- `--indicators INDICATORS`: Indicator columns to include (default: EMA20 EMA50 EMA100 EMA200 sma20 sma50 rsi macd_line macd_signal macd_hist stoch_k stoch_d atr bb_upper bb_middle bb_lower vwap)
- `--max-expected-time MAX`: Maximum expected time in candles (default: 12)
- `--token-limit LIMIT`: Maximum token usage limit (default: 50000)
- `--input-token-price PRICE`: Price per input token for cost calculation (default: 0.0)
- `--output-token-price PRICE`: Price per output token for cost calculation (default: 0.0)
- `--max-cost COST`: Maximum dollar cost for token usage (default: 0.0, disabled)
- `--output-dir DIR`: Output directory for results (default: backtest_results)

#### Examples:
```bash
# Backtest BTCUSDT using the last 400 candles
python -m backtesting.backtest --lookback 400 -s BTCUSDT

# Backtest multiple symbols with custom settings and token cost limits
python -m backtesting.backtest --lookback 200 -s BTCUSDT ETHUSDT --interval 4h --step 5 --token-limit 10000 --input-token-price 0.0001 --output-token-price 0.0001
```

### Backtesting Output

Results are saved in the specified output directory:
- `summary.json`: Overall summary with success rates and token usage
- `{symbol}_results.json`: Detailed results for each symbol
- `{symbol}_results.csv`: CSV format for easy analysis

Each trade result includes:
- Timestamp
- Predicted scenario (up/down)
- Confidence level
- Entry/target/stop prices
- Expected time
- Actual outcome (success/failure/timeout)
- Return percentage
- Analysis explanation

### Performance Metrics

The backtesting provides comprehensive metrics:
- **Trade Statistics**: Total trades, wins, losses, timeouts
- **Success Rate**: Percentage of profitable trades
- **Return Analysis**: Total return, average return per trade
- **Benchmarking**: Buy & hold return comparison
- **Outperformance**: Strategy return vs buy & hold
- **Cost Tracking**: Token usage and monetary cost

## Project Structure

- `main.py`: Entry point for the analysis
- `config.py`: Configuration and environment variables
- `backtesting/`: Historical testing module
  - `backtest.py`: Backtesting implementation
- `engine/`: Core analysis engine
  - `llm.py`: LLM integration
  - `llm_prompt.py`: Analysis prompts
  - `plot.py`: Chart plotting
- `crypto_data/`: Data fetching and processing
  - `getter.py`: Binance API client
  - `indicators.py`: Technical indicators
- `helper/`: Utility functions
  - `utils.py`: Telegram and formatting utilities

## Environment Variables

- `OPENROUTER_API_KEY`: API key for OpenRouter (LLM service)
- `MODEL_NAME`: LLM model to use
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `TELEGRAM_CHAT_ID`: Telegram chat ID for notifications
