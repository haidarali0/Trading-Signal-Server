from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import MFIIndicator
import pandas as pd

# ==========================================
# LIQUIDATION ESTIMATION
# ==========================================
def get_estimate_liquidations(df, oi_series, leverage=15, candles=10):
    df = df.iloc[-candles:]
    oi_series = oi_series.iloc[-candles:]
    
    if len(df) != len(oi_series):
        raise ValueError(f"Length mismatch: df has {len(df)} rows, oi_series has {len(oi_series)} rows.")
    
    if not df.index.equals(oi_series.index):
        raise ValueError("Index mismatch: df.index and oi_series.index are not identical.")
    
    df['pct_change'] = df['close'].pct_change().fillna(0)
    df['liq_est'] = abs(df['pct_change']) * oi_series * leverage
    
    return df['liq_est']

# ==========================================
# TREND INDICATORS
# ==========================================
def get_trend_indicators(df):
    close = df["close"]
    trend = pd.DataFrame({
        "EMA20": EMAIndicator(close, 20).ema_indicator(),
        "EMA50": EMAIndicator(close, 50).ema_indicator(),
        "EMA100": EMAIndicator(close, 100).ema_indicator(),
        "EMA200": EMAIndicator(close, 200).ema_indicator(),
        "SMA20": SMAIndicator(close, 20).sma_indicator(),
        "SMA50": SMAIndicator(close, 50).sma_indicator(),
    }, index=df.index)
    return trend

# ==========================================
# MOMENTUM INDICATORS
# ==========================================
def get_momentum_indicators(df):
    close = df["close"]
    macd = MACD(close)
    stoch = StochasticOscillator(df["high"], df["low"], close, 14)
    
    momentum = pd.DataFrame({
        "RSI": RSIIndicator(close, 14).rsi(),
        "MACD_line": macd.macd(),
        "MACD_signal": macd.macd_signal(),
        "MACD_hist": macd.macd_diff(),
        "Stoch_k": stoch.stoch(),
        "Stoch_d": stoch.stoch_signal(),
    }, index=df.index)
    return momentum

# ==========================================
# VOLATILITY INDICATORS
# ==========================================
def get_volatility_indicators(df):
    close = df["close"]
    atr = AverageTrueRange(df["high"], df["low"], close, 14).average_true_range()
    bb = BollingerBands(close, 20, 2)
    
    volatility = pd.DataFrame({
        "ATR": atr,
        "BB_upper": bb.bollinger_hband(),
        "BB_middle": bb.bollinger_mavg(),
        "BB_lower": bb.bollinger_lband(),
    }, index=df.index)
    return volatility

# ==========================================
# VOLUME / FLOW INDICATORS
# ==========================================
def get_volume_indicators(df):
    close = df["close"]
    vwap = (close * df["volume"]).cumsum() / df["volume"].cumsum()
    mfi = MFIIndicator(df["high"], df["low"], close, df["volume"], 14).money_flow_index()
    
    volume = pd.DataFrame({
        "VWAP": vwap,
        "MFI": mfi
    }, index=df.index)
    return volume

# ==========================================
# MAIN FUNCTION TO RETURN ALL INDICATORS
# ==========================================
def calculate_indicators(df, oi_series, leverage=15, n_for_oi=150):
    # Liquidation
    print("CALCULATING INDICATORS --------")
    liq = get_estimate_liquidations(df, oi_series, leverage=leverage, candles=n_for_oi)
    print("1- Liquidations : Ok")
    if isinstance(liq, pd.Series):
        liq_df = liq.rename("Liquidations").to_frame()
    else:
        liq_df = pd.DataFrame({"Liquidations": liq}, index=df.index)
    
    trend_indicators = get_trend_indicators(df)
    print("2- tread indicators : OK")
    momentum_indicators = get_momentum_indicators(df)
    print("3- momentum indicators : OK")
    volatility_indicators = get_volatility_indicators(df)
    print("4- volatility indicators : OK")
    volume_indicators = get_volume_indicators(df)
    print("5- volume indicators : OK")
    # Merge all groups
    indicators = pd.concat([
        liq_df,
        trend_indicators,
        momentum_indicators,
        volatility_indicators,
        volume_indicators
    ], axis=1)
    print("Done ----")
    return indicators