import json
import numpy as np
from openai import OpenAI
import json_repair
from engine.llm_prompt import prompt
from config import OPENROUTER_API_KEY as API, MODEL_NAME

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
    print("Sending request to LLM...")
    formatted_prompt = prompt.format(symbol=symbol, time_frame=time_frame, info=info)
    response = client.chat.completions.create(
    model=MODEL_NAME,
    messages=[
            {
                "role": "user",
                "content": formatted_prompt
            }
            ],
    extra_body={"reasoning": {"enabled": True}}
    )
    res = json_repair.loads(response.choices[0].message.content)
    return res