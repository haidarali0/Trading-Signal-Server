from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
import pandas as pd

def calculate_indicators(df):
    close = df["close"]
    ema20  = EMAIndicator(close, 20).ema_indicator()
    ema50  = EMAIndicator(close, 50).ema_indicator()
    ema100 = EMAIndicator(close, 100).ema_indicator()
    ema200 = EMAIndicator(close, 200).ema_indicator()

    sma20 = SMAIndicator(close, 20).sma_indicator()
    sma50 = SMAIndicator(close, 50).sma_indicator()

    rsi = RSIIndicator(close, 14).rsi()

    macd = MACD(close)
    macd_line = macd.macd()
    signal = macd.macd_signal()
    hist = macd.macd_diff()

    stoch = StochasticOscillator(df["high"], df["low"], df["close"], 14)
    k = stoch.stoch()
    d = stoch.stoch_signal()

    atr = AverageTrueRange(df["high"], df["low"], df["close"], 14).average_true_range()

    bb = BollingerBands(close, 20, 2)
    bb_upper = bb.bollinger_hband()
    bb_middle = bb.bollinger_mavg()
    bb_lower = bb.bollinger_lband()

    vwap = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

    indicators = pd.DataFrame({
        "EMA20": ema20,
        "EMA50": ema50,
        "EMA100": ema100,
        "EMA200": ema200,
        "atr": atr,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "vwap": vwap,
        "macd_line": macd_line,
        "macd_signal": signal,
        "macd_hist": hist,
        "stoch_k": k,
        "stoch_d": d,
        "rsi": rsi,
        "sma20": sma20,
        "sma50": sma50
    })

    return indicators