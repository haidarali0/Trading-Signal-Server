import requests
import html
from typing import Dict, Any
from config import TELEGRAM_BOT_TOKEN as BOT_TOKEN, TELEGRAM_CHAT_ID as CHAT_ID
from textwrap import dedent


# Sends a chart image with a caption to a Telegram channel using the Bot API.
# Function: send_telegram_message
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



# Formats trade signal data into a clean HTML-styled message with emoji confidence indicators.
# Function: format_minimal_pro
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
    return dedent(f"""
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
    """)

# Calculates gain percentage, loss percentage, and risk-reward ratio based on trade scenario direction.
# Function: calculate_ratios
def calculate_ratios(res: Dict[str, Any]) -> Dict[str, float]:
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