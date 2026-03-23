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
    VOL_WINDOW = 20
    BASE_URL = "https://api.binance.com"
    ORDERBOOK_LIMIT = 100
    TRADES_LIMIT = 500
    FR_LIMIT = 20
    GF_LIMIT = 5

# ==========================================
# HTTP REQUEST HELPER
# ==========================================

def fetch(endpoint=None, params=None, alt=False, full_url=None):
    if not full_url:
        base_url = Config.BASE_URL
        if alt:
            base_url =base_url.replace("api", "fapi")
        url = f"{base_url}{endpoint}"
    else:
        url = full_url
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

def get_candles(symbol, interval, limit):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
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

    # Keep time as datetime for analysis
    df["time"] = pd.to_datetime(df["time"], unit="ms").dt.strftime('%d-%m-%Y %H:%M:%S')
    df["time_idx"] =  df["time"].copy()
    df.set_index("time_idx", inplace=True)

    numeric = ["open","high","low","close","volume"]
    df[numeric] = df[numeric].astype(float)

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

def get_orderbook(symbol, limit):
    params = {
        "symbol": symbol,
        "limit": limit
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

    denom = bid_volume + ask_volume + 1e-9
    imbalance = (bid_volume - ask_volume) / denom

    return {
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "spread": spread,
        "orderbook_imbalance": imbalance
    }


# ==========================================
# 5. RECENT TRADES
# ==========================================

def get_trades(symbol, limit):
    params = {
        "symbol":symbol,
        "limit": limit 
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

    ratio = buy_volume / (buy_volume + sell_volume + 1e-9)

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
    vol_value = vol.iloc[-1] if not np.isnan(vol.iloc[-1]) else 0

    return {
        "volatility": vol_value
    }


# ==========================================
# 8. FULL MARKET SNAPSHOT
# ==========================================

def get_market_snapshot(candles, symbol, limit):
    bids, asks = get_orderbook(symbol, limit)
    trades = get_trades(symbol, limit)

    snapshot = {
            "price": candles["close"].iloc[-1],
            "orderbook": orderbook_features(bids, asks),    # bid_volume, ask_volume, spread, imbalance
            "trade_flow": trade_flow_features(trades),      # buy_volume, sell_volume, buy_sell_ratio, trade_count
            "volatility": volatility_features(candles)     # volatility
        }

    return snapshot


# ==========================================
# 9. OPEN INTEREST (OI) SERIES
# ==========================================

def get_oi_series(symbol, interval, limit):
    params = {
        "symbol": symbol,
        "period": interval,
        "limit": limit
    }

    res = fetch("/futures/data/openInterestHist", params, alt=True)
    df = pd.DataFrame(res)

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.strftime('%d-%m-%Y %H:%M:%S')
    df['sumOpenInterest'] = df['sumOpenInterest'].astype(float)

    return df.set_index('timestamp')['sumOpenInterest']



# ==========================================
# Funding Rate
# ==========================================
def get_funding_rate(symbol, limit):
    params = {
        "symbol": symbol,
        "limit": limit
    }
    res = fetch("/fapi/v1/fundingRate", params, alt=True)
    
    df = pd.DataFrame(res)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"], unit="ms").dt.strftime('%d-%m-%Y %H:%M:%S')
    df["fundingRate"] = df["fundingRate"].astype(float)
    
    return df[["fundingTime", "fundingRate"]]



# ==========================================
# Greedy Fear Index
# ==========================================
def get_fear_greed_index(limit=None):
    url = "https://api.alternative.me/fng/"
    params = {
              "limit": limit or Config.GF_LIMIT,
              "format": "json"
              }
    res = fetch(full_url="https://api.alternative.me/fng/", params=params)
    
    # Extract data
    data = res["data"]
    df = pd.DataFrame(data)
    
    # Convert types
    df["value"] = df["value"].astype(float)
    df["value_classification"] = df["value_classification"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s').dt.strftime('%d-%m-%Y %H:%M:%S')    
    return df[["timestamp", "value", "value_classification"]]




# ===========================
# FULL MARKET DATA USING CONFIG
# ===========================
def get_full_market_data_config(only_candles = False) -> dict:
    """
    Returns all main market data as a grouped dictionary using Config values:
    - Candles
    - Market Snapshot
    - Open Interest
    - Funding Rate
    - Fear & Greed Index
    """
    print("FETCHING DATA -------")
    # --- Candles ---
    candles = get_candles(symbol=Config.SYMBOL, interval=Config.INTERVAL, limit=Config.LIMIT)
    print("1- candles : OK")
    if only_candles:
        print("Done -------")
        return {"candles" : candles}
    # --- Market Snapshot ---
    snapshot = get_market_snapshot(candles=candles, symbol=Config.SYMBOL, limit=Config.LIMIT)
    print("2- snapshot : OK")
    # --- Open Interest ---
    oi = get_oi_series(symbol=Config.SYMBOL, interval=Config.INTERVAL, limit=Config.LIMIT)
    print("3- OI series : OK")
    # --- Funding Rate ---
    frate = get_funding_rate(symbol=Config.SYMBOL, limit=Config.FR_LIMIT)
    print("4- Funding Rate : OK")
    # --- Fear & Greed Index ---
    fng = get_fear_greed_index(limit=Config.GF_LIMIT)  # usually last 30 days
    print("5- Fear Greedy Index : OK")
    # --- Grouped dictionary ---
    print("Done ---------")
    data = {
        "candles": candles,
        "snapshot": snapshot,
        "open_interest": oi,
        "funding_rate": frate,
        "fear_greedy_index": fng
    }
    
    return data


# ===========================
# Example usage
# ===========================
if __name__ == "__main__":
    data = get_full_market_data_config()
    
    print("Candles (last 5 rows):\n", data["candles"].tail())
    print("\nMarket Snapshot:\n", data["snapshot"])
    print("\nOpen Interest (last 5 rows):\n", data["open_interest"].tail())
    print("\nFunding Rate (last 5 rows):\n", data["funding_rate"].tail())
    print("\nFear & Greed Index (last 5 rows):\n", data["fear_greed_index"].tail())