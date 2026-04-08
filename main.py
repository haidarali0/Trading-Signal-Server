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
CHAT_ID =1028815240#"-1003520393965" # "1028815240"  

# === SETTINGS ===
SYMBOLS = ["BTCUSDT", "BNBUSDT", "ZECUSDT", "ETHUSDT", "PEPEUSDT", "XRPUSDT", "DOGEUSDT", "SOLUSDT", "FUNUSDT", "ASTRUSDT", "ETHFIUSDT"]
LIMIT = 400
INTERVAL = "1h"
SEND_VALUES = 30
HIGHER_TIMEFRAMES = ["4h"]


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
    stop  = html.escape(str(result["stop_loss"]))
    time_h = html.escape(str(result["expected_time"]))
    gain_ratio = round(result['gain_ratio'], 2)
    loss_ratio = round(result['loss_ratio'], 2)
    rr =  round(result['rr'], 2)
    analysis = html.escape(result['analysis'])

    emoji = "🟢" if confidence >= 0.75 else "🟡" if confidence >= 0.6 else "🔴"

    return f"""
<b>{html.escape(result['Symbol'])}</b>
{emoji} <b>{scenario}</b> | Conf: <b>{confidence}</b>
━━━━━━━━━━━━━━━━━━
⏬ Entry point : {entry}
💰 Expected Price: ~ <b>{target}</b>
   Stop Price : ~ <b>{stop}</b>
⏱ Expected Time: next {time_h} candles.
⏫ Gain Ratio : ~ {gain_ratio} %
⏫ Loss Ratio : ~ {loss_ratio} %
⏫ RR : ~ {rr} %
━━━━━━━━━━━━━━━━━━
🧠 {analysis}
"""

# ============================
# CALCULATE GAIN RATIO
# ============================
def calculate_ratios(res: Dict[str, Any]) -> Dict[str, float]:
    """Calculate gain percentage and risk-reward ratio."""
    if res['scenario'].lower().strip() == "up":
        gain = res['target_price'] - res['entry_price']
        risk = res['entry_price'] - res['stop_loss']
    else:
        gain = res['entry_price'] - res['target_price']
        risk = res['stop_loss'] - res['entry_price']

    if gain <= 0:
        raise ValueError("[ISSUE] in target price")
    if risk <= 0:
        rr = 0.0
    else:
        rr = gain / risk

    gain_pct = (gain / res['entry_price']) * 100
    stop_pct = (risk / res['entry_price']) * 100
    return {"gain_ratio": gain_pct, "loss_ratio": stop_pct, "rr": rr}

# ============================
# MAIN LOOP
# ============================
def run_analysis(symbols: List[str]) -> None:
  llm_res = None
  crypto_res = {s:[] for s in symbols}
  try:
    for symbol in symbols:
     for _ in range(2):
        print("====================================")
        print(f"Analyzing {symbol}")
        Config.SYMBOL = symbol
        Config.LIMIT = 300
        Config.INTERVAL = "1h"
        basic_interval = Config.INTERVAL
        Config.HIGHER_TIMEFRAMES = ["4h"]
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
        llm_res = res
        crypto_res[Config.SYMBOL].append(res['scenario'].lower().strip())
        print(f"LLM response for {Config.SYMBOL}: {res}")
        if len(crypto_res[Config.SYMBOL]) < 2:
              print(f"Not enough signals for {Config.SYMBOL}, skipping...")
              continue
        elif any(["no_trade"==r for r in crypto_res[Config.SYMBOL]]):
              print(f"no_trade {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, skipping...")
              continue
        elif not (all([r == "up" for r in crypto_res[Config.SYMBOL]]) or all([r == "down" for r in crypto_res[Config.SYMBOL]])):
               print(f"Mismtash {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, skipping...")
               continue
        else:
            print(f"Consistent signals {crypto_res[Config.SYMBOL]} for {Config.SYMBOL}, proceeding...")
        plot_data(res['target_price'], res['stop_loss'],  res['expected_time'], basic_interval, symbol)
        print("✔ Chart image saved!")
        try:
            res |= calculate_ratios(res)
        except ValueError as e:
            print("===========================")
            print(e)
            continue

        # Send Telegram if signal strong enough
        if res['confidence'] >= 0.7 and res["gain_ratio"] >=1:
            res['Symbol'] = Config.SYMBOL
            msg = format_minimal_pro(res)
            send_telegram_message(msg)
        else:
            print(res)
  except Exception as e:
      print(f"error {e}")

if __name__ == "__main__":
    run_analysis(SYMBOLS)