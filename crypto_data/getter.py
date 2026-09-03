import requests
import pandas as pd
import numpy as np


# Configuration container for Binance API parameters including symbol, intervals, limits, and base URL.
class Config:
    SYMBOL = "BTCUSDT"
    INTERVAL = "5m"
    LIMIT = 500
    HIGHER_TIMEFRAMES = ["15m", "1h", "4h"]
    ORDERBOOK_LIMIT = 100
    TRADES_LIMIT = 500
    VOL_WINDOW = 20
    BASE_URL = "https://api.binance.com"


# Sends HTTP GET request to Binance API and returns JSON response with error handling.
# Function: fetch
def fetch(endpoint, params=None):
    url = f"{Config.BASE_URL}{endpoint}"
    r = requests.get(url, params=params)
    if r.status_code != 200:
        raise Exception(f"Binance API error {r.status_code}: {r.text}")
    data = r.json()
    if isinstance(data, dict) and "code" in data:
        raise Exception(f"Binance returned error: {data}")
    return data


# Fetches OHLCV candle data from Binance and returns as a formatted pandas DataFrame.
# Function: get_candles
def get_candles(interval=None, limit=None, start_time=None, end_time=None):
    params = {
        "symbol": Config.SYMBOL,
        "interval": interval or Config.INTERVAL,
    }
    if start_time:
        params["startTime"] = int(pd.to_datetime(start_time).timestamp() * 1000)
    if end_time:
        params["endTime"] = int(pd.to_datetime(end_time).timestamp() * 1000)
    if limit and not (start_time and end_time):
        params["limit"] = limit or Config.LIMIT
    data = fetch("/api/v3/klines", params)
    df = pd.DataFrame(
        data,
        columns=[
            "time","open","high","low","close","volume",
            "close_time","quote_volume","trades",
            "taker_base","taker_quote","ignore"
        ]
    )
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    #df["time"] = df["time"].dt.tz_localize("Asia/Damascus")
    df["time"] = df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")

    numeric = ["open","high","low","close","volume"]
    df[numeric] = df[numeric].astype(float)
    #df.to_csv(f"candles_{Config.INTERVAL}.csv", index=False)
    return df

# Retrieves candles for the base interval and all configured higher timeframes.
# Function: get_multi_timeframe
def get_multi_timeframe():
    data = {}
    data[Config.INTERVAL] = get_candles()
    for tf in Config.HIGHER_TIMEFRAMES:
        data[tf] = get_candles(interval=tf)
    return data


# Fetches current order book depth with bid and ask prices/quantities from Binance.
# Function: get_orderbook
def get_orderbook():
    params = {
        "symbol": Config.SYMBOL,
        "limit": Config.ORDERBOOK_LIMIT
    }
    data = fetch("/api/v3/depth", params)
    bids = pd.DataFrame(data["bids"], columns=["price","qty"]).astype(float)
    asks = pd.DataFrame(data["asks"], columns=["price","qty"]).astype(float)
    return bids, asks


# Calculates order book metrics including volumes, spread, and imbalance ratio.
# Function: orderbook_features
def orderbook_features(bids, asks):
    bid_volume = bids["qty"].sum()
    ask_volume = asks["qty"].sum()
    best_bid = bids.iloc[0]["price"]
    best_ask = asks.iloc[0]["price"]
    spread = best_ask - best_bid
    imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
    return {
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "spread": spread,
        "orderbook_imbalance": imbalance
    }


# Retrieves recent trade history from Binance with price and quantity data.
# Function: get_trades
def get_trades():
    params = {
        "symbol": Config.SYMBOL,
        "limit": Config.TRADES_LIMIT
    }
    data = fetch("/api/v3/trades", params)
    df = pd.DataFrame(data)
    df["price"] = df["price"].astype(float)
    df["qty"] = df["qty"].astype(float)
    return df


# Computes buy/sell volumes, ratio, and trade count from recent trades.
# Function: trade_flow_features
def trade_flow_features(trades):
    buy_volume = trades[trades["isBuyerMaker"] == False]["qty"].sum()
    sell_volume = trades[trades["isBuyerMaker"] == True]["qty"].sum()
    ratio = buy_volume / (sell_volume + 1e-9)
    return {
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "buy_sell_ratio": ratio,
        "trade_count": len(trades)
    }


# Calculates rolling standard deviation of log returns as a volatility measure.
# Function: volatility_features
def volatility_features(df):
    returns = np.log(df["close"]).diff()
    vol = returns.rolling(Config.VOL_WINDOW).std()
    return {
        "volatility": vol.iloc[-1]
    }


# Aggregates current price, orderbook, trade flow, and volatility into a comprehensive market snapshot.
# Function: get_market_snapshot
def get_market_snapshot(candles):
    snapshot = {
        "price": candles["close"].iloc[-1],
        "bid_volume": 0.0,
        "ask_volume": 0.0,
        "spread": 0.0,
        "orderbook_imbalance": 0.0,
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "buy_sell_ratio": 1.0,
        "trade_count": 0,
    }
    try:
        bids, asks = get_orderbook()
        snapshot.update(orderbook_features(bids, asks))
    except requests.exceptions.RequestException as exc:
        print(f"[Binance] order book unavailable; using defaults: {exc}")
    try:
        trades = get_trades()
        snapshot.update(trade_flow_features(trades))
    except requests.exceptions.RequestException as exc:
        print(f"[Binance] recent trades unavailable; using defaults: {exc}")
    snapshot.update(volatility_features(candles))
    return snapshot
