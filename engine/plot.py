import pandas as pd
import numpy as np
import mplfinance as mpf
import json


def build_projection_index(history_index, projection_steps):
    if len(history_index) < 2:
        return pd.DatetimeIndex([history_index[-1]] if len(history_index) else pd.to_datetime(["1970-01-01"]))
    last_diff = history_index[-1] - history_index[-2]
    return history_index[-1] + last_diff * pd.Index(range(1, int(projection_steps) + 1))


def build_projection_series(full_index, price, total_rows, projection_steps):
    projection_steps = max(1, int(projection_steps))
    vals = [np.nan] * total_rows
    start_index = max(0, total_rows - projection_steps)
    for i in range(start_index, total_rows):
        vals[i] = price
    return pd.Series(vals, index=full_index)


#Generates a candlestick chart with indicators, projected target/stop levels, and shaded zones, then saves to cache
# Function: plot_data
def plot_data(target_price, stop_loss_price, expected_time, timeframe, symbol):
    with open("cache/request.json", "r") as f:
        data = json.load(f)

    payload = data.get("llm_payload", data)
    price_history = payload.get("price_history")
    if not price_history:
        raise ValueError("Request cache is missing price_history data for plotting")

    df = pd.DataFrame(price_history)
    if df.empty:
        raise ValueError(f"Request cache for {symbol} has no price history data for plotting")

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

    projection_steps = max(1, int(expected_time))
    if len(df) >= 2:
        projection_index = build_projection_index(df.index, projection_steps)
        empty_rows = pd.DataFrame(np.nan, index=projection_index, columns=df.columns)
        df = pd.concat([df, empty_rows])
    else:
        last_ts = df.index[-1]
        projection_index = pd.DatetimeIndex([last_ts])
        empty_rows = pd.DataFrame(np.nan, index=projection_index, columns=df.columns)
        df = pd.concat([df, empty_rows])

    # --- Addplots ---
    apds = []

    indicator_group = None
    if any(col in df.columns for col in ["EMA20", "EMA50", "EMA100", "EMA200"]):
        indicator_group = "EMA"
    elif any(col in df.columns for col in ["sma20", "sma50"]):
        indicator_group = "SMA"
    elif any(col in df.columns for col in ["bb_upper", "bb_middle", "bb_lower"]):
        indicator_group = "BB"

    if indicator_group == "EMA":
        for col in ["EMA20", "EMA50", "EMA100", "EMA200"]:
            if col in df.columns:
                apds.append(mpf.make_addplot(df[col], width=1))
    elif indicator_group == "SMA":
        for col in ["sma20", "sma50"]:
            if col in df.columns:
                apds.append(mpf.make_addplot(df[col], width=1))
    elif indicator_group == "BB":
        for col in ["bb_upper", "bb_middle", "bb_lower"]:
            if col in df.columns:
                apds.append(mpf.make_addplot(df[col], width=1))

    # --- Prepare series for target, stop, current ---
    full_index = df.index
    # Use the last valid close, but never index with a negative offset that is longer than the frame.
    last_close = df["Close"].iloc[-1] if not df.empty else 0.0

    target_series = build_projection_series(full_index, target_price, len(df), projection_steps)
    stop_series = build_projection_series(full_index, stop_loss_price, len(df), projection_steps)
    current_series = build_projection_series(full_index, last_close, len(df), projection_steps)

    # --- Lines ---
    for series, color, width in [
        (target_series, 'green', 1.5),
        (stop_series, 'red', 1.5),
        (current_series, 'gray', 1.0),
    ]:
        if pd.notna(series).any():
            apds.append(mpf.make_addplot(series, type='line', width=width, color=color, linestyle='--' if color == 'gray' else None))

    # --- Zones (light color) ---
    green_zone = build_projection_series(full_index, target_price, len(df), projection_steps)
    red_zone = build_projection_series(full_index, stop_loss_price, len(df), projection_steps)
    for series, color in [(green_zone, 'green'), (red_zone, 'red')]:
        if pd.notna(series).any():
            apds.append(mpf.make_addplot(series, type='line', width=10, color=color, alpha=0.1))

    # --- Plot ---
    chart_title = f"{symbol} {timeframe} chart"
    if indicator_group:
        chart_title += f" with {indicator_group}"
    else:
        chart_title += ""

    output_path = f"cache/{symbol}_{timeframe}_{indicator_group or 'price'}.png"

    fig, axlist = mpf.plot(
        df,
        type='candle',
        style='charles',
        volume=True,
        addplot=apds,
        title=chart_title,
        ylabel="Price",
        ylabel_lower="Volume",
        figsize=(12, 8),
        returnfig=True
    )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    fig.savefig("cache/chart.png", dpi=300, bbox_inches="tight")
    return output_path