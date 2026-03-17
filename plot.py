import pandas as pd
import numpy as np
import mplfinance as mpf
import json
# ====== Your data ======
with open("request.json", "r") as f:
    data = json.load(f)
# ====== Convert to DataFrame ======
df = pd.DataFrame(data["price_history"])

# Convert time
df["time"] = pd.to_datetime(df["time"])
df.set_index("time", inplace=True)

# Sort (IMPORTANT for plotting)
df = df.sort_index()

# Rename columns for mplfinance
df.rename(columns={
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume"
}, inplace=True)

# ====== Add indicators to plot ======
apds = []

for ema in ["EMA20", "EMA50", "EMA100", "EMA200"]:
    if ema in df.columns:
        apds.append(mpf.make_addplot(df[ema], width=1))

# # === SMA ===
# for sma in ["sma20", "sma50"]:
#     if sma in df.columns:
#         apds.append(mpf.make_addplot(df[sma], linestyle='dotted'))

# === Bollinger Bands ===
# apds.append(mpf.make_addplot(df["bb_upper"], linestyle='dashed'))
# apds.append(mpf.make_addplot(df["bb_middle"], linestyle='solid'))
# apds.append(mpf.make_addplot(df["bb_lower"], linestyle='dashed'))

# === VWAP ===
# apds.append(mpf.make_addplot(df["vwap"], linestyle='dashdot'))

# === MACD (panel 1) ===
apds.append(mpf.make_addplot(df["macd_line"], panel=1))
# apds.append(mpf.make_addplot(df["macd_signal"], panel=1))
# apds.append(mpf.make_addplot(df["macd_hist"], type='bar', panel=1))

# === RSI (panel 2) ===
apds.append(mpf.make_addplot(df["rsi"], panel=2))

# # === Stochastic (panel 3) ===
# apds.append(mpf.make_addplot(df["stoch_k"], panel=3))
# apds.append(mpf.make_addplot(df["stoch_d"], panel=3))

# ====== Plot ======
mpf.plot(
    df,
    type='candle',
    style='charles',   # closest to TradingView look
    volume=True,
    addplot=apds,
    title="Candlestick Chart",
    ylabel="Price",
    ylabel_lower="Volume",
    figsize=(12, 8),
     savefig=dict(
        fname="chart.png",
        dpi=300,          # higher quality
        bbox_inches="tight"
    )
)