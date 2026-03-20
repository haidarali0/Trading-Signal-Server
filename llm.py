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
    return [to_float(v) for v in series.tail(n).tolist()][::-1]


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

    "price_history" : [
        {
            "time": t,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v
        }
        for t, o, h, l, c, v in zip(
            last_n(candles["time"], n),
            last_n(candles["open"], n),
            last_n(candles["high"], n),
            last_n(candles["low"], n),
            last_n(candles["close"], n),
            last_n(candles["volume"], n)
        )
    ]
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
        for i in range(n):
            row = indicators.iloc[len(indicators)-1-i]
            for col_name, value in row.items():
               data["price_history"][i][col_name] = value
    # multi timeframe
    if higher_tf is not None:
        data['market']['current_time_frame'] = time_frame
        data["higher_timeframes"] = {}

        for tf, df in higher_tf.items():
            data["higher_timeframes"][tf] = json.loads(build_llm_market_input(symbol=symbol, time_frame=tf, candles=df['candles'], n=n//2))
    return json.dumps(data, indent=2)

def inference(info, symbol, time_frame):
    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API,
    )
    prompt = f"""
You are a professional crypto scalping analyst specializing in order flow, market microstructure, and multi-timeframe confluence.

Analyze the following real-time market data for {symbol} on the {time_frame} timeframe.

Use the latest candles and ALL provided data in "Market Data", including:

TECHNICAL INDICATORS:
- EMA and SMA (trend direction)
- RSI (momentum / overbought-oversold)
- MACD (momentum shifts)
- Bollinger Bands (volatility)
- Stochastic (K and D)

MARKET STRUCTURE:
- Support and resistance levels
- Trend structure (HH/HL or LH/LL)

ADVANCED DATA:
- Market microstructure:
  • Spread (tight = strong liquidity, wide = weak liquidity)
  • Order book imbalance (bullish if > 0, bearish if < 0)
  • Bid vs Ask volume dominance
- Trade flow:
  • Buy vs sell volume
  • Buy/Sell ratio (bullish if > 1, bearish if < 1)
  • Trade intensity (trade_count)
- Volatility:
  • Use to validate realistic price movement
- Higher timeframes (e.g., 4h):
  • Use as trend confirmation (do NOT trade against strong HTF trend unless strong reversal signals exist)

IMPORTANT RULES:
- The CURRENT PRICE MUST be used as the ENTRY PRICE.
- Prediction must be strictly short-term (within the next 12 hours).
- You MUST combine indicators (confluence). Never rely on a single signal.
- Give strong weight to:
  1. Order flow (trade_flow)
  2. Order book imbalance
  3. Higher timeframe trend
- If signals conflict, reduce confidence.

- You may also use Fibonacci retracement levels if relevant.

OUTPUT REQUIREMENTS:
- Output MUST be valid JSON ONLY (no extra text).
- All numeric values MUST be numbers (NOT strings).
- Do NOT include null values.

Return EXACTLY this JSON structure:

{{
  "entry_price": <number>,
  "scenario": "up" | "down",
  "confidence": <number between 0 and 1>,
  "target_price": <number>,
  "expected_time_hours": <number>,
  "analysis": "<max 80 words>"
}}

STRICT CONSTRAINTS:
- scenario MUST be ONLY "up" or "down"
- confidence MUST be between 0 and 1
- expected_time_hours MUST be > 0 and <= 12
- target_price MUST be realistic based on volatility and liquidity
- analysis MUST be concise and reflect key confluence factors

INTERPRETATION GUIDE (MANDATORY):
- Bullish bias if:
  • Buy/Sell ratio > 1
  • Orderbook imbalance > 0
  • Bid volume > Ask volume
- Bearish bias if:
  • Buy/Sell ratio < 1
  • Orderbook imbalance < 0
  • Ask volume > Bid volume
- Low spread + high volume = strong move potential
- High volatility = allow wider target
- Align with higher timeframe trend for higher confidence

Market Data:
{info}
"""
    print("Sending request to LLM...")
    response = client.chat.completions.create(
    model="google/gemini-2.5-flash-lite-preview-09-2025",#anthropic/claude-opus-4.6",#"deepseek/deepseek-chat-v3-0324", #"minimax/minimax-m2.5",
    messages=[
            {
                "role": "user",
                "content":prompt
            }
            ],
    extra_body={"reasoning": {"enabled": True}}
    )
    res = json_repair.loads(response.choices[0].message.content)
    return res