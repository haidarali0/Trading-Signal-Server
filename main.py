import json
import requests
from typing import Dict, Any, List

from engine.llm import build_llm_market_input, inference
from crypto_data.getter import Config, get_full_market_data_config
from engine.plot import plot_data

from crypto_data.indicators import calculate_indicators

import html

# ============================
# TELEGRAM FUNCTIONS
def send_telegram_message(msg: str, image_path: str = "cache/chart.png") -> None:
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
    gain_ratio = f"{float(result['gain_pct']):.2f}"
    analysis = html.escape(result['analysis'])
    if "stop_loss_price" in result:
        stop_loss = f"{float(result['stop_loss_price']):.2f}"
        stop_ratio = f"{float(result['loss_pct']):.2f}"
        rr = f"{float(result['rr']):.2f}"
    else:
        stop_loss = "-----"
        rr = "------"

    emoji = "🟢" if confidence >= 0.75 else "🟡" if confidence >= 0.6 else "🔴"

    return f"""
<b>📊 {html.escape(result['Symbol'])}</b>
{emoji} <b>{scenario.upper()}</b> | Confidence: <b>{confidence}</b>

━━━━━━━━━━━━━━━━━━
📍 <b>Trade Setup</b>
• Entry: <b>{entry}</b>
• Target: <b>{target}</b>
• Stop Loss: <b>{stop_loss}</b>

━━━━━━━━━━━━━━━━━━
📈 <b>Performance</b>
• Gain: <b>{gain_ratio}%</b>
• Loss: <b>{stop_ratio}%</b>
• Gain-Loss Ratio: <b>{rr}</b>

━━━━━━━━━━━━━━━━━━
⏱ <b>Time Horizon</b>
• Expected: <b>{time_h}h</b>

━━━━━━━━━━━━━━━━━━
🧠 <b>Analysis</b>
{analysis}
"""

# ============================
# CALCULATE GAIN RATIO
# ============================
from typing import Dict, Any

def calculate_ratios(res: Dict[str, Any]) -> Dict[str, float]:
    """Calculate gain %, and optionally loss % and risk-reward ratio."""

    scenario = res.get('scenario', '').lower().strip()

    if scenario == "no_trade":
        return {
            "gain_pct": 0.0
        }

    entry = res.get('entry_price')
    target = res.get('target_price')
    stop = res.get('stop_loss_price')  # may be missing

    if entry is None or target is None:
        raise ValueError("[ISSUE] entry_price or target_price missing")

    # --- Gain ---
    if scenario == "up":
        gain = target - entry
    elif scenario == "down":
        gain = entry - target
    else:
        raise ValueError("Invalid scenario")

    if gain <= 0:
        print(res)
        raise ValueError("[ISSUE] invalid target price")

    gain_pct = (gain / entry) * 100

    # --- If NO stop loss → return only gain ---
    if stop is None:
        return {
            "gain_pct": gain_pct
        }

    # --- Loss ---
    if scenario == "up":
        loss = entry - stop
    else:  # down
        loss = stop - entry

    if loss <= 0:
        print(res)
        print(11111111)
        raise ValueError("[ISSUE] invalid stop loss price")

    loss_pct = (loss / entry) * 100
    rr = gain / loss

    return {
        "gain_pct": gain_pct,
        "loss_pct": loss_pct,
        "rr": rr
    }

# ============================
# MAIN LOOP
# ============================
# === TELEGRAM BOT INFO ===
BOT_TOKEN = "8663098456:AAG3kZt8GT5m_xZmYhGxhSZ1QadS-6ov3V4"
CHAT_ID =1028815240#"-1003520393965" # "1028815240"  

# === SETTINGS ===
SYMBOLS = ["BTCUSDT", "BNBUSDT", "ZECUSDT", "ETHUSDT", "PEPEUSDT", "XRPUSDT", "DOGEUSDT", "SOLUSDT"]




def run_analysis(symbols: List[str]) -> None:
    for symbol in symbols:
        print("====================================")
        print(f"Analyzing {symbol}")
        Config.SYMBOL = symbol
        Config.LIMIT = 350
        Config.INTERVAL = "1h"
        basic_interval = Config.INTERVAL
        Config.HIGHER_TIMEFRAMES = ["4h"]
        N = 40

        full_data = get_full_market_data_config()
        indicators = calculate_indicators(full_data['candles'], full_data['open_interest'])
     
        higher_tf_data = {}
        higher_indicators = {}
        for tf in Config.HIGHER_TIMEFRAMES:
            Config.INTERVAL = tf
            df_tf = get_full_market_data_config()
            higher_tf_data[tf] = df_tf
            higher_indicators[tf] = calculate_indicators(df_tf['candles'], df_tf['open_interest']) 


        # Prepare LLM input
        market_info = build_llm_market_input(
            Config.SYMBOL, basic_interval, full_data=full_data,
            n=N, indicators=indicators, higher_tf=higher_tf_data, higher_tf_indicators=higher_indicators
        )

        with open("cache/request.json", "w") as f:
            json.dump(market_info, f, indent=2)
            print("✔ Request saved!")
        break
        # LLM inference
        res = inference(market_info, Config.SYMBOL, basic_interval)
        try:
            res |= calculate_ratios(res)
        except ValueError as e:
            print("===========================")
            print(e)
            continue
        # Send Telegram if signal strong enough
        if res['scenario'] != "no_trade" and res['confidence'] >= 0.6 and res["gain_pct"] >= 1:
            print(res)
            res['Symbol'] = Config.SYMBOL
            plot_data(res['target_price'], res["stop_loss_price"], res['expected_time_hours'], basic_interval, symbol)
            print("✔ Chart image saved!")
            msg = format_minimal_pro(res)
            send_telegram_message(msg)
        else:
            print(res)


if __name__ == "__main__":
    run_analysis(SYMBOLS)