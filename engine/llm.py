import json
import numpy as np
from openai import OpenAI
import json_repair
from engine.llm_prompt import prompt_1, prompt_2


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
    full_data,
    indicators=None,
    higher_tf=None,
    higher_tf_indicators=None,
    n=10
):
    """
    Build structured input for LLM using last N rows of data.
    """
    print("BUILDING LLM MSG")
    candles = full_data['candles']
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

    if "snapshot" in full_data:
       data["full_market_snapshot"] = full_data["snapshot"]
    if "funding_rate" in full_data:
       data['funding_rate_data'] = full_data['funding_rate'].to_dict(orient="records")
    if "fear_greedy_index" in full_data:
       data['fear_greedy_index'] = full_data['fear_greedy_index'].to_dict(orient="records")

    # indicators history
    if indicators is not None:
        for i in range(n):
            row = indicators.iloc[len(indicators)-1-i]
            for col_name, value in row.items():
               data["price_history"][i][col_name] = value
    # multi timeframe
    if higher_tf is not None and higher_tf_indicators is not None:
        data['market']['current_time_frame'] = time_frame
        data["higher_timeframes"] = {}
         
        for (tf, df), (tf, ind) in zip(higher_tf.items(), higher_tf_indicators.items()):
            data["higher_timeframes"][tf] = build_llm_market_input(symbol=symbol, time_frame=tf, full_data=df, indicators=ind, n=n//2)
   
    return data

def inference(info, symbol, time_frame):
    print("START ANAYLSIS BY LLM")
    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API,
    )
    print("Sending request to LLM...")
    prompt = prompt_2.format(symbol=symbol, time_frame=time_frame, info=info)
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