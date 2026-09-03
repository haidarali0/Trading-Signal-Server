import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen/qwen3-235b-a22b-2507")

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading Configuration
DEFAULT_SYMBOLS = ["BTCUSDT", "BNBUSDT", "ZECUSDT", "ETHUSDT", "PEPEUSDT", "XRPUSDT", "DOGEUSDT", "SOLUSDT", "FUNUSDT", "ASTRUSDT", "ETHFIUSDT"]
DEFAULT_LIMIT = 400
DEFAULT_INTERVAL = "1h"
DEFAULT_SEND_VALUES = 30
DEFAULT_HIGHER_TIMEFRAMES = ["4h"]
DEFAULT_INDICATORS = [
    "EMA20", "EMA50", "EMA100", "EMA200",
    "sma20", "sma50",
    "rsi",
    "macd_line", "macd_signal", "macd_hist",
    "stoch_k", "stoch_d",
    "atr",
    "bb_upper", "bb_middle", "bb_lower",
    "vwap"
]

# Analysis Configuration
DEFAULT_N = 40
CONFIDENCE_THRESHOLD = 0.7
GAIN_RATIO_THRESHOLD = 1.0