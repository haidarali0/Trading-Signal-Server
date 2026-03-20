import pandas as pd
import numpy as np
import mplfinance as mpf
import json

def plot_data(target_price, expected_time, timeframe, symbol):
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

    last_diff = df.index[-1] - df.index[-2]
    new_index = [df.index[-1] + last_diff * (i+1) for i in range(int(expected_time))]
    empty_rows = pd.DataFrame(np.nan, index=new_index, columns=df.columns)
    df = pd.concat([df, empty_rows])
    apds = []

    for ema in ["EMA20", "EMA50", "EMA100", "EMA200"]:
        if ema in df.columns:
            apds.append(mpf.make_addplot(df[ema], width=1))
    target_series = pd.Series([target_price if i == df.index[-1] else None for i in df.index], index=df.index)

    target_plt = mpf.make_addplot(
        target_series,
        type='scatter',
        markersize=100,
        marker='o',   
        color='green'
    )
    apds.append(target_plt)
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
    ax = axlist[0] 
    fig.savefig("cache/chart.png", dpi=300, bbox_inches="tight")