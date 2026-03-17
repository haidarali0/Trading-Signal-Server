import requests
import pandas as pd
import numpy as np
import time
import mplfinance as mpf
import matplotlib.pyplot as plt
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from llm import build_llm_market_input, inference
from getter import get_candles, get_market_snapshot, Config
import json
# === TELEGRAM BOT INFO ===
BOT_TOKEN = "8663098456:AAG3kZt8GT5m_xZmYhGxhSZ1QadS-6ov3V4"
CHAT_ID = "1028815240"
# === SETTINGS ===
SYMBOL = "DOGEUSDT"
INTERVAL = "4h"
LIMIT = 400
SEND_VALUES = 30


# ============================
# SEND TEXT MESSAGE TO TELEGRAM
# ============================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}

    try:
        response = requests.post(url, json=payload, timeout=10)
        print("✔ Message delivered to Telegram." if response.status_code == 200 else "✖ Telegram error:", response.text)
    except Exception as e:
        print("❌ Telegram send failed:", e)


# ============================
# SEND IMAGE TO TELEGRAM
# ============================
def send_telegram_image(image_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as img:
        payload = {"chat_id": CHAT_ID}
        files = {"photo": img}
        requests.post(url, data=payload, files=files)
    print("📸 Chart sent to Telegram.")



# ============================
# BUILD MESSAGE
# ============================
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


# ============================
# PLOT TRADINGVIEW STYLE CHART
# ============================

def plot_chart(df):
    df_plot = df.copy()

    # === Indicators ===
    df_plot["EMA20"] = EMAIndicator(df_plot["close"], 20).ema_indicator()
    df_plot["EMA50"] = EMAIndicator(df_plot["close"], 50).ema_indicator()
    df_plot["EMA100"] = EMAIndicator(df_plot["close"], 100).ema_indicator()
    df_plot["EMA200"] = EMAIndicator(df_plot["close"], 200).ema_indicator()

    bb = BollingerBands(df_plot["close"], 20, 2)
    df_plot["BB_upper"] = bb.bollinger_hband()
    df_plot["BB_middle"] = bb.bollinger_mavg()
    df_plot["BB_lower"] = bb.bollinger_lband()

    # === Slice only last SEND_VALUES rows ===
    df_plot = df_plot.tail(SEND_VALUES)

    # Candle numbering (1 → SEND_VALUES)
    df_plot["Label"] = range(1, len(df_plot) + 1)


    apds = [
        # mpf.make_addplot(df_plot["EMA20"], color="#1f77b4"),
        # mpf.make_addplot(df_plot["EMA50"], color="#ff7f0e"),
        # mpf.make_addplot(df_plot["EMA100"], color="#2ca02c"),
        # mpf.make_addplot(df_plot["EMA200"], color="#d62728"),
        # mpf.make_addplot(df_plot["BB_upper"], color="#9467bd"),
        # mpf.make_addplot(df_plot["BB_middle"], color="#7f7f7f"),
        # mpf.make_addplot(df_plot["BB_lower"], color="#9467bd"),
    ]
    # === Plot ===
    fig, ax = mpf.plot(
        df_plot,
        type="candle",
        style="charles",
        addplot=apds,
        volume=True,
        returnfig=True,
        figsize=(14, 8)
    )

    # Correct axis for price
    price_ax = ax[1]

    # === Add labels above candles ===
    for i, (idx, row) in enumerate(df_plot.iterrows()):
        price_ax.text(
            i,
            row["high"] * 1.002,
            str(row["Label"]),
            fontsize=7,
            color="white",
            ha="center"
        )

    # === Save ===
    image_path = "chart.png"
    fig.savefig(image_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return image_path
# ============================
# MAIN LOOP
# ============================
while True:
    Config.SYMBOL = "SOLUSDT"
    Config.LIMIT =300
    Config.INTERVAL = "30m"
    basic_interval = Config.INTERVAL
    Config.HIGHER_TIMEFRAMES = ["1h"]
    df = get_candles()
    indicators = calculate_indicators(df)
    snapshot = get_market_snapshot(df)
    extra_data = {}
    for i in  Config.HIGHER_TIMEFRAMES:
         Config.INTERVAL = i
         df_i = get_candles()
         #indicators = calculate_indicators(df)
         extra_data[Config.INTERVAL] = {"candles": df_i}
    market_info = build_llm_market_input(Config.SYMBOL, basic_interval, df, snapshot, n=100, indicators=indicators, higher_tf=extra_data)
    with open("request.json", "w") as f:
        json.dump(json.loads(market_info), f, indent=2)
        print("request has been saved !!!")
    res = inference(market_info, Config.SYMBOL, basic_interval)
    send_telegram(res)
    break
    # chart_path = plot_chart(df)
    # send_telegram_image(chart_path)

    # print("Sent to Telegram.")
    # time.sleep(60)