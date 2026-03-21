import pandas as pd
import numpy as np
import mplfinance as mpf
import json

def plot_data(target_price, stop_loss_price, expected_time, timeframe, symbol):
    # --- Load data ---
    with open("cache/request.json", "r") as f:
        data = json.load(f)
    df = pd.DataFrame(data["price_history"])
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    df = df.sort_index()

    df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    }, inplace=True)

    # --- Extend index for expected time ---
    last_diff = df.index[-1] - df.index[-2]
    new_index = [df.index[-1] + last_diff * (i+1) for i in range(int(expected_time))]
    empty_rows = pd.DataFrame(np.nan, index=new_index, columns=df.columns)
    df = pd.concat([df, empty_rows])

    # --- Addplots ---
    apds = []

    # EMAs
    for ema in ["EMA20", "EMA50", "EMA100", "EMA200"]:
        if ema in df.columns:
            apds.append(mpf.make_addplot(df[ema], width=1))

    # --- Prepare series for target, stop, current ---
    full_index = df.index
    last_close = df["Close"].iloc[-(expected_time+1)]

    # Create series full length, only fill last expected_time candles
    def create_line_series(price):
        vals = [np.nan]*len(df)
        for i in range(-int(expected_time), 0):
            vals[i] = price
        return pd.Series(vals, index=full_index)

    target_series = create_line_series(target_price)
    stop_series = create_line_series(stop_loss_price)
    current_series = create_line_series(last_close)

    # --- Lines ---
    apds.append(mpf.make_addplot(target_series, type='line', width=1.5, color='green'))
    apds.append(mpf.make_addplot(stop_series, type='line', width=1.5, color='red'))
    apds.append(mpf.make_addplot(current_series, type='line', width=1.0, color='gray', linestyle='--'))

    # --- Zones (light color) ---
    # Simply add semi-transparent horizontal lines with width ~ fill
    def create_zone_series(top, bottom):
        vals = [np.nan]*len(df)
        for i in range(-int(expected_time), 0):
            vals[i] = top
        return pd.Series(vals, index=full_index)

    green_zone = create_zone_series(target_price, last_close)
    red_zone = create_zone_series(stop_loss_price, last_close)

    apds.append(mpf.make_addplot(green_zone, type='line', width=10, color='green', alpha=0.1))
    apds.append(mpf.make_addplot(red_zone, type='line', width=10, color='red', alpha=0.1))

    # --- Plot ---
    fig, axlist = mpf.plot(
        df,
        type='candle',
        style='charles',
        volume=True,
        addplot=apds,
        title=f"{symbol} Chart with timeframe {timeframe} with EMAs",
        ylabel="Price",
        ylabel_lower="Volume",
        figsize=(12, 8),
        returnfig=True
    )

    fig.savefig("cache/chart.png", dpi=300, bbox_inches="tight")