import json
import numpy as np
from openai import OpenAI
import json_repair
API = "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"


def to_float(v):
    """Convert numpy types to python floats"""
    if isinstance(v, (np.float32, np.float64, np.float16)):
        return float(v)
    return v


def last_n(series, n):
    """Return last n values as clean list"""
    return [to_float(v) for v in series.tail(n).tolist()]


def build_llm_market_input(
    symbol,
    time_frame,
    candles,
    snapshot=None,
    indicators=None,
    higher_tf=None,
    n=10
):
    """
    Build structured input for LLM using last N rows of data.
    """
    data = {
        "market": {
            "symbol": symbol,
        },

        "price_history": {
            "open": last_n(candles["open"], n),
            "high": last_n(candles["high"], n),
            "low": last_n(candles["low"], n),
            "close": last_n(candles["close"], n),
            "volume": last_n(candles["volume"], n),
            "time" : last_n(candles['time'],n)
        }
    }
    if snapshot is not None:
        snapshot = {k: float(v) for k, v in snapshot.items()}
        data['market_microstructure'] =   {
            "spread": snapshot["spread"],
            "orderbook_imbalance": snapshot["orderbook_imbalance"],
            "bid_volume": snapshot["bid_volume"],
            "ask_volume": snapshot["ask_volume"]
        }
        data['trade_flow'] = {
            "buy_volume": snapshot["buy_volume"],
            "sell_volume": snapshot["sell_volume"],
            "buy_sell_ratio": snapshot["buy_sell_ratio"],
            "trade_count": snapshot["trade_count"]
        },

        data["volatility"] = snapshot["volatility"],
        data['market']["current_price"]= snapshot["price"]

    # indicators history
    if indicators is not None:
            data["indicators"] = {
            col: last_n(indicators[col], n)
            for col in indicators.columns
        }
    # multi timeframe
    if higher_tf is not None:
        data['market']['current_time_frame'] = time_frame
        data["higher_timeframes"] = {}

        for tf, df in higher_tf.items():
            data["higher_timeframes"][tf] = build_llm_market_input(symbol=symbol, time_frame=tf, candles=df['candles'], n=n//2)
    return json.dumps(data, indent=2)

def inference(info):
    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API,
    )
    prompt = """You are a professional quantitative market analyst specializing in short-term cryptocurrency price dynamics.

            Your task is to analyze structured market data and estimate the probability that the current price trend will continue upward or downward before reversing.

            Focus on short-term trend continuation.

            You must evaluate the following factors when analyzing the data:

            * Price momentum and recent candle structure
            * Trend alignment (EMA / SMA relationships)
            * Momentum indicators (RSI, MACD, Stochastic)
            * Volatility context (ATR, Bollinger Bands)
            * Market microstructure (orderbook imbalance, spread)
            * Trade flow (buy vs sell pressure)
            * Volume behavior
            * Multi-indicator confirmation or divergence

            Your goal is NOT to predict an exact future price.
            Instead estimate the probability that price will reach certain percentage movements **before the trend reverses**.

            Estimate the probability for the following movements:

            Upward continuation:

            * +1%
            * +5%
            * +10%

            Downward continuation:

            * −1%
            * −5%
            * −10%

            Rules:

            1. Probabilities must be numbers between **0 and 1**.
            2. Base your reasoning only on the provided market data.
            3. Consider trend strength, volatility regime, and indicator alignment.
            4. If indicators conflict, probabilities should be closer to neutral.
            5. If strong trend confirmation exists, larger targets may still have meaningful probability.
            6. Output must be valid JSON only.
            7. Do not include any text outside JSON.

            Output format (strict):
 
            {
            "traget_pair": "crypto_pair",
            "target_timeframe": "4h",
            "upward_probabilities": {
            "1_percent": number,
            "5_percent": number,
            "10_percent": number
            },
            "downward_probabilities": {
            "1_percent": number,    
            "5_percent": number,
            "10_percent": number,
            },
            "analysis": "short explanation summarizing the reasoning behind the probabilities"
            }

            Market Data: <info>

            """
    # First API call with reasoning
    response = client.chat.completions.create(
    model="anthropic/claude-opus-4.6",
    messages=[
            {
                "role": "user",
                "content":prompt.replace("<info>",info)
            }
            ],
    extra_body={"reasoning": {"enabled": True}}
    )
    res = json_repair.loads(response.choices[0].message.content)
    return res