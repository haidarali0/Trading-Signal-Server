import json
import numpy as np
from pathlib import Path
from openai import OpenAI
import json_repair
from engine.llm_prompt import prompt as default_prompt
from config import OPENROUTER_API_KEY as API, MODEL_NAME


#Convert numpy types to python floats
# Function: to_float
def to_float(v):
    if isinstance(v, (np.float32, np.float64, np.float16)):
        return float(v)
    return v

#Return last n values as clean list
# Function: last_n
def last_n(series, n):
    return [to_float(v) for v in series.tail(n).tolist()][::-1]

#Constructs a structured JSON input for LLM inference with price history, micro-structure data, indicators, and optional higher timeframe context.
# Function: build_llm_market_input
def build_llm_market_input(
    symbol,
    time_frame,
    candles,
    snapshot=None,
    indicators=None,
    higher_tf=None,
    quant_data=None,
    web_data=None,
    n=10
):
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
    # --- indicators history ---
    if indicators is not None:
        for i in range(n):
            row = indicators.iloc[len(indicators)-1-i]
            for col_name, value in row.items():
               data["price_history"][i][col_name] = value
    # --- quant model output ---
    if quant_data is not None:
        data["quant"] = quant_data

    # --- web context ---
    if web_data is not None:
        data["web_context"] = {
            "symbol": web_data.get("symbol"),
            "query_topics": web_data.get("query_topics", []),
            "query": web_data.get("query"),
            "context": web_data.get("context"),
            "results": web_data.get("results", []),
        }

    # --- multi timeframe ---
    if higher_tf is not None:
        data['market']['current_time_frame'] = time_frame
        data["higher_timeframes"] = {}
        for tf, df in higher_tf.items():
            data["higher_timeframes"][tf] = json.loads(build_llm_market_input(symbol=symbol, time_frame=tf, candles=df['candles'], n=n//2))
    return json.dumps(data, indent=2)


#Sends formatted prompt to OpenRouter LLM, parses JSON response, and returns the result with token usage statistics.
# Function: inference
def load_prompt_texts(prompt_files):
    if not prompt_files:
        return None
    paths = [Path(path).expanduser() for path in prompt_files]
    prompt_texts = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"LLM prompt file not found: {path}")
        prompt_texts.append(path.read_text(encoding="utf-8"))
    return prompt_texts


def select_prompt_text(prompt_texts, model_index):
    if not prompt_texts:
        return None
    if len(prompt_texts) == 1:
        return prompt_texts[0]
    if model_index < len(prompt_texts):
        return prompt_texts[model_index]
    return prompt_texts[-1]


def inference(info, symbol, time_frame, web_context=None, model_name=None, prompt_text=None):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API,
    )
    selected_model = model_name or MODEL_NAME
    print(f"[LLM] stage: sending request for {symbol} @ {time_frame} with {selected_model}...")
    template = prompt_text if prompt_text is not None else default_prompt
    formatted_prompt = template.format(
        symbol=symbol,
        time_frame=time_frame,
        info=info,
        web_context=web_context or "No external context available.",
    )
    response = client.chat.completions.create(
        model=selected_model,
        messages=[
            {
                "role": "user",
                "content": formatted_prompt
            }
        ],
        extra_body={"reasoning": {"enabled": True}}
    )
    res = json_repair.loads(response.choices[0].message.content)
    usage = response.usage
    print(f"[LLM] response received for {symbol} @ {time_frame}. Usage: {usage}")
    return res, usage
