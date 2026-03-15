import requests
import pandas as pd
import numpy as np


# ==========================================
# CONFIGURATION
# ==========================================

class Config:
    SYMBOL = "BTCUSDT"
    INTERVAL = "5m"
    LIMIT = 500
    HIGHER_TIMEFRAMES = ["15m", "1h", "4h"]
    ORDERBOOK_LIMIT = 100
    TRADES_LIMIT = 500
    VOL_WINDOW = 20
    BASE_URL = "https://api.binance.com"


# ==========================================
# HTTP REQUEST HELPER
# ==========================================

def fetch(endpoint, params=None):

    url = f"{Config.BASE_URL}{endpoint}"

    r = requests.get(url, params=params)

    if r.status_code != 200:
        raise Exception(f"Binance API error {r.status_code}: {r.text}")

    data = r.json()

    if isinstance(data, dict) and "code" in data:
        raise Exception(f"Binance returned error: {data}")

    return data


# ==========================================
# 1. CANDLES (OHLCV)
# ==========================================

def get_candles(interval=None, limit=None):

    params = {
        "symbol": Config.SYMBOL,
        "interval": interval or Config.INTERVAL,
        "limit": limit or Config.LIMIT
    }

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
    df["time"] = df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")

    numeric = ["open","high","low","close","volume"]
    df[numeric] = df[numeric].astype(float)
    df.to_csv(f"candles_{Config.INTERVAL}.csv", index=False)
    return df


# ==========================================
# 2. MULTI TIMEFRAME DATA
# ==========================================

def get_multi_timeframe():

    data = {}

    data[Config.INTERVAL] = get_candles()

    for tf in Config.HIGHER_TIMEFRAMES:
        data[tf] = get_candles(interval=tf)

    return data


# ==========================================
# 3. ORDER BOOK
# ==========================================

def get_orderbook():

    params = {
        "symbol": Config.SYMBOL,
        "limit": Config.ORDERBOOK_LIMIT
    }

    data = fetch("/api/v3/depth", params)

    bids = pd.DataFrame(data["bids"], columns=["price","qty"]).astype(float)
    asks = pd.DataFrame(data["asks"], columns=["price","qty"]).astype(float)

    return bids, asks


# ==========================================
# 4. ORDER BOOK FEATURES
# ==========================================

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


# ==========================================
# 5. RECENT TRADES
# ==========================================

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


# ==========================================
# 6. TRADE FLOW FEATURES
# ==========================================

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


# ==========================================
# 7. VOLATILITY FEATURES
# ==========================================

def volatility_features(df):

    returns = np.log(df["close"]).diff()

    vol = returns.rolling(Config.VOL_WINDOW).std()

    return {
        "volatility": vol.iloc[-1]
    }


# ==========================================
# 8. FULL MARKET SNAPSHOT
# ==========================================

def get_market_snapshot(candles):

    # candles
    # orderbook
    bids, asks = get_orderbook()

    # trades
    trades = get_trades()

    snapshot = {}

    snapshot["price"] = candles["close"].iloc[-1]

    snapshot.update(orderbook_features(bids, asks))
    snapshot.update(trade_flow_features(trades))
    snapshot.update(volatility_features(candles))

    return snapshot


# ==========================================
# EXAMPLE USAGE
# ==========================================
