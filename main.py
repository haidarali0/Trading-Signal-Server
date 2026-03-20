import json
import requests
from typing import Dict, Any, List

from engine.llm import build_llm_market_input, inference
from crypto_data.getter import get_candles, get_market_snapshot, Config
from engine.plot import plot_data

from crypto_data.indicators import calculate_indicators

import html

# === TELEGRAM BOT INFO ===
BOT_TOKEN = "8663098456:AAG3kZt8GT5m_xZmYhGxhSZ1QadS-6ov3V4"
CHAT_ID =-1003520393965#"-1003520393965" # "1028815240"  

# === SETTINGS ===
SYMBOLS = ["BTCUSDT", "BNBUSDT", "ZECUSDT", "ETHUSDT", "PEPEUSDT", "XRPUSDT", "DOGEUSDT", "SOLUSDT"]
LIMIT = 400
INTERVAL = "1h"
SEND_VALUES = 30
HIGHER_TIMEFRAMES = ["4h"]


# ============================
# TELEGRAM FUNCTIONS
def send_telegram_message(msg: str, image_path: str = "chart.png") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as img:
        payload = {"chat_id": CHAT_ID, "caption": msg, "parse_mode": "HTML"}
        files = {"photo": img}
        response = requests.post(url, data=payload, files=files, timeout=10)
        if response.status_code == 200:
            print("📸 Chart sent to Telegram.")
        else:
            print("✖ Telegram error:", response.text)



def format_minimal_pro(result: dict) -> str:
    scenario = html.escape(result["scenario"].upper())
    confidence = round(result["confidence"], 2)
    entry = html.escape(str(result["entry_price"]))
    target = html.escape(str(result["target_price"]))
    time_h = html.escape(str(result["expected_time_hours"]))
    gain_ratio = round(result['gain_ratio'], 2)
    analysis = html.escape(result['analysis'])

    emoji = "🟢" if confidence >= 0.75 else "🟡" if confidence >= 0.6 else "🔴"

    return f"""
<b>{html.escape(result['Symbol'])}</b>
{emoji} <b>{scenario}</b> | Conf: <b>{confidence}</b>
━━━━━━━━━━━━━━━━━━
⏬ Entry point : {entry}
💰 Expected Price: ~ <b>{target}</b>
⏱ Expected Time: {time_h}h
⏫ Gain Ratio : ~ {gain_ratio} %
━━━━━━━━━━━━━━━━━━
🧠 {analysis}
"""

# ============================
# CALCULATE GAIN RATIO
# ============================
def calculate_gain_ratio(res: Dict[str, Any]) -> float:
    """Calculate gain ratio based on scenario direction."""
    if res['scenario'].lower().strip() == "up":
        diff = res['target_price'] - res['entry_price']
    else:
        diff = res['entry_price'] - res['target_price']

    if diff <= 0:
        raise ValueError("[ISSUE] in target price")
    return diff / res['entry_price'] * 100


# ============================
# MAIN LOOP
# ============================
def run_analysis(symbols: List[str]) -> None:
    for symbol in symbols:
        print("====================================")
        print(f"Analyzing {symbol}")
        Config.SYMBOL = symbol
        Config.LIMIT = 300
        Config.INTERVAL = "1h"
        basic_interval = Config.INTERVAL
        Config.HIGHER_TIMEFRAMES = HIGHER_TIMEFRAMES
        N = 40

        # Get main timeframe data
        df = get_candles()
        indicators = calculate_indicators(df)  # Make sure this function exists
        snapshot = get_market_snapshot(df)

        # Fetch higher timeframe candles
        higher_tf_data = {}
        for tf in Config.HIGHER_TIMEFRAMES:
            Config.INTERVAL = tf
            df_tf = get_candles()
            higher_tf_data[tf] = {"candles": df_tf}

        # Prepare LLM input
        market_info = build_llm_market_input(
            Config.SYMBOL, basic_interval, df, snapshot,
            n=N, indicators=indicators, higher_tf=higher_tf_data
        )

        # Save request for reference
        with open("cache/request.json", "w") as f:
            json.dump(json.loads(market_info), f, indent=2)
            print("✔ Request saved!")

        # LLM inference
        res = inference(market_info, Config.SYMBOL, basic_interval)
        plot_data(res['target_price'], res['expected_time_hours'], basic_interval, symbol)
        print("✔ Chart image saved!")
        try:
            res['gain_ratio'] = calculate_gain_ratio(res)
        except ValueError as e:
            print("===========================")
            print(e)
            continue

        # Send Telegram if signal strong enough
        if res['confidence'] >= 0.6 and res["gain_ratio"] >= 1:
            res['Symbol'] = Config.SYMBOL
            msg = format_minimal_pro(res)
            send_telegram_message(msg)
        else:
            print(res)


if __name__ == "__main__":
    run_analysis(SYMBOLS)