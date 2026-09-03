"""Local web control panel for live trading analysis and backtests.

Run from the project root with: .\.venv\Scripts\python.exe dashboard\app.py
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import sys
from pathlib import Path as _Path_for_root
_ROOT = _Path_for_root(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config import (
    DEFAULT_SYMBOLS,
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_HIGHER_TIMEFRAMES,
    DEFAULT_INDICATORS,
    DEFAULT_N,
    CONFIDENCE_THRESHOLD,
    GAIN_RATIO_THRESHOLD,
    MODEL_NAME,
)
from crypto_data.getter import Config as CryptoConfig, get_candles, get_market_snapshot
from crypto_data.indicators import calculate_indicators
from ml_builder import list_records, append_record, export_records, update_record
from web.search import search_web_context

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
PROMPT_DIR = ROOT / "prompts"
SAVED_CONFIGS_PATH = ROOT / "cache" / "saved_configs.json"
STOP_REQUEST_PATH = ROOT / "cache" / "stop_requested.json"
PROMPT_DIR.mkdir(exist_ok=True)
SAVED_CONFIGS_PATH.parent.mkdir(exist_ok=True)
LOCK = threading.Lock()
RUN = {"process": None, "mode": None, "status": "Idle", "started_at": None, "finished_at": None, "command": [], "output": [], "error": None, "exit_code": None, "progress": {"current": 0, "total": 0, "percent": 0.0}, "symbol_progress": {}, "total_progress_seen": False}
DASHBOARD_LIVE_INTERVAL = "1m"
DATA_REFRESH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dashboard-refresh")


def set_stop_request(active: bool, mode: str | None = None):
    try:
        STOP_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"active": bool(active), "mode": mode or RUN.get("mode"), "timestamp": datetime.now(timezone.utc).isoformat()}
        STOP_REQUEST_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def read_saved_configs() -> list[dict]:
    try:
        if not SAVED_CONFIGS_PATH.exists():
            return []
        data = json.loads(SAVED_CONFIGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("configs", [])
        if not isinstance(data, list):
            return []
        return [safe_json_value(item) for item in data if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError):
        return []


def write_saved_configs(configs: list[dict]) -> list[dict]:
    normalized = [safe_json_value(item) for item in (configs or []) if isinstance(item, dict)]
    SAVED_CONFIGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVED_CONFIGS_PATH.write_text(json.dumps(normalized, indent=2, default=str), encoding="utf-8")
    return normalized


def read_json(path: Path, fallback=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def safe_json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_json_value(item) for item in value]
    return value

def safe_prompt_name(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    name = Path(name).name
    if not name:
        return ""
    if not name.lower().endswith(".txt"):
        name = f"{name}.txt"
    return name


def list_prompt_files():
    PROMPT_DIR.mkdir(exist_ok=True)
    return sorted([p.name for p in PROMPT_DIR.glob("*.txt") if p.is_file()])


def read_prompt_file(name: str) -> str | None:
    safe_name = safe_prompt_name(name)
    if not safe_name:
        return None
    path = PROMPT_DIR / safe_name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def write_prompt_file(name: str, content: str) -> str:
    safe_name = safe_prompt_name(name)
    if not safe_name:
        raise ValueError("Invalid prompt file name.")
    path = PROMPT_DIR / safe_name
    path.write_text(content or "", encoding="utf-8")
    return safe_name


def words(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").replace(",", " ").split() if item.strip()]


def read_env_values() -> dict[str, str]:
    values = {}
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def masked(value: str) -> str:
    if not value:
        return ""
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "saved"


def save_env_values(updates: dict[str, str]):
    existing = read_env_values()
    for key, value in updates.items():
        if value:
            existing[key] = value
            os.environ[key] = value
    lines = [f"{key}={value}" for key, value in existing.items()]
    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def option(command: list[str], flag: str, value, multiple=False):
    values = words(value) if multiple else [str(value).strip()] if value is not None else []
    if values and all(values):
        command.extend([flag, *values])


def as_float(payload: dict, key: str, default: float = 0.0) -> float:
    try:
        value = payload.get(key, default)
        return float(default if value in (None, "") else value)
    except (TypeError, ValueError):
        return default


def as_int(payload: dict, key: str, default: int = 0) -> int:
    try:
        value = payload.get(key, default)
        return int(float(default if value in (None, "") else value))
    except (TypeError, ValueError):
        return default


def has_openrouter_key() -> bool:
    values = read_env_values()
    return bool(values.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY"))


def validate_run_payload(payload: dict, mode: str) -> str | None:
    if not has_openrouter_key():
        return "OpenRouter API key is required. Add it in Settings first."
    models = words(payload.get("model_names"))
    if len(set(models)) != len(models):
        return "Voting models must not contain duplicates."
    iterations = as_int(payload, "iterations", 1)
    if iterations < 1:
        return "Iterations must be at least 1."
    if models and iterations < len(models):
        return "Iterations must be at least the number of voting models."
    if as_int(payload, "web_search_max_results", 1) < 1:
        return "Web max results must be at least 1."
    if mode == "live":
        if not 0 <= as_float(payload, "confidence_threshold", as_float(payload, "confidence", 0.7)) <= 1:
            return "Confidence must be between 0 and 1."
        if as_float(payload, "gain_ratio_threshold", as_float(payload, "gain_ratio", 1.0)) < 0:
            return "Gain ratio threshold must be greater than or equal to 0."
        if as_int(payload, "limit", 1) < 1:
            return "Candle limit must be at least 1."
        if payload.get("quant_limit") not in (None, "") and as_int(payload, "quant_limit", 1) < 1:
            return "Quant candle limit must be at least 1."
        quant_test_size = as_float(payload, "quant_test_size", 0.2)
        if not 0.01 <= quant_test_size <= 0.99:
            return "Quant test size must be between 0.01 and 0.99."
    else:
        lookback = as_int(payload, "lookback", as_int(payload, "limit", 400))
        step = as_int(payload, "step", 10)
        n = as_int(payload, "n", 40)
        max_expected_time = as_int(payload, "max_expected_time", 12)
        if lookback < 1:
            return "Lookback candles must be at least 1."
        if step < 1 or step >= lookback:
            return "Step must be at least 1 and smaller than lookback."
        if n < 1:
            return "LLM input candles must be at least 1."
        if max_expected_time < 1:
            return "Max expected time must be at least 1."
        if lookback <= n + max_expected_time:
            return "Lookback must be greater than LLM input candles plus max expected time."
        if as_int(payload, "token_limit", 1) < 1:
            return "Token limit must be at least 1."
        if as_float(payload, "input_token_price", 0.0) < 0 or as_float(payload, "output_token_price", 0.0) < 0:
            return "Token prices must be greater than or equal to 0."
        if as_float(payload, "max_cost", 0.0) < 0:
            return "Maximum cost must be greater than or equal to 0."
        if not str(payload.get("output_dir", "backtest_results")).strip():
            return "Output directory must not be empty."
    if as_int(payload, "quant_shift", 1) < 1:
        return "Quant shift must be at least 1."
    if as_int(payload, "quant_predict_rows", 1) < 1:
        return "Quant prediction rows must be at least 1."
    if as_float(payload, "quant_direction_threshold", 0.001) < 0:
        return "Direction threshold must be greater than or equal to 0."
    return None


def log(line: str):
    with LOCK:
        RUN["output"] = (RUN["output"] + [line.rstrip()])[-500:]
        total_match = re.search(r"\[progress\]\s+TOTAL\s+(\d+)\/(\d+)", line, re.I)
        if total_match:
            current = int(total_match.group(1))
            total = int(total_match.group(2))
            RUN["total_progress_seen"] = True
            RUN["progress"] = {"current": current, "total": total, "percent": (current / total * 100.0) if total else 0.0}
            return

        match = re.search(r"\[progress\]\s+(\S+)\s+(\d+)\/(\d+)", line, re.I)
        if match:
            symbol = match.group(1)
            current = int(match.group(2))
            total = int(match.group(3))
            RUN.setdefault("symbol_progress", {})[symbol] = {"current": current, "total": total}
            if not RUN.get("total_progress_seen", False):
                progress_by_symbol = RUN.get("symbol_progress", {})
                if progress_by_symbol:
                    current_total = sum(item["current"] for item in progress_by_symbol.values())
                    total_total = sum(item["total"] for item in progress_by_symbol.values())
                    percent = (current_total / total_total * 100.0) if total_total else 0.0
                    RUN["progress"] = {"current": current_total, "total": total_total, "percent": percent}


def consume(process: subprocess.Popen):
    assert process.stdout
    for line in process.stdout:
        log(line)
    code = process.wait()
    with LOCK:
        RUN["exit_code"] = code
        RUN["finished_at"] = datetime.now(timezone.utc).isoformat()
        stop_message = None
        for line in RUN["output"]:
            if re.search(r"(stopping backtest|stopped backtest|token limit|cost limit|stop signal sent)", line, re.I):
                stop_message = line.strip()
                break
        if RUN.get("status") == "Stopping" or stop_message:
            RUN["status"] = "Stopped"
            RUN["error"] = stop_message or "Process was stopped before completion."
        else:
            RUN["status"] = "Completed" if code == 0 else "Failed"
            RUN["error"] = None if code == 0 else f"Process exited with code {code}. See the console output."
        if RUN["progress"].get("total"):
            RUN["progress"]["current"] = RUN["progress"]["total"]
            RUN["progress"]["percent"] = 100.0
        else:
            RUN["progress"] = {"current": 0, "total": 0, "percent": 0.0}
        set_stop_request(False, RUN.get("mode"))
    log(f"[dashboard] Finished with exit code {code}.")


def stop_active_process() -> tuple[bool, str]:
    with LOCK:
        process = RUN.get("process")
        if not process or process.poll() is not None:
            return False, "No task is running."

        RUN["status"] = "Stopping"
        RUN["error"] = RUN.get("error") or "Stopping…"
        RUN["finished_at"] = None
        set_stop_request(True, RUN.get("mode"))
    log("[dashboard] Stop requested. The live loop will exit on the next safe checkpoint.")
    return True, "Stop signal sent."


def build_live(payload: dict) -> list[str]:
    command = [sys.executable, "-u", "main.py"]
    aliases = {"confidence": "confidence_threshold", "gain_ratio": "gain_ratio_threshold"}
    for old, new in aliases.items():
        if old in payload and new not in payload:
            payload[new] = payload[old]
    option(command, "--symbols", payload.get("symbols"), True)
    for flag, key in [("--interval", "interval"), ("--limit", "limit"), ("--quant-limit", "quant_limit"), ("--quant-input-data", "quant_input_data"), ("--quant-test-size", "quant_test_size"), ("--quant-model", "quant_model"), ("--quant-target-mode", "quant_target_mode"), ("--quant-direction-threshold", "quant_direction_threshold"), ("--quant-input-set", "quant_input_set"), ("--quant-transform", "quant_transform"), ("--quant-output-target", "quant_output_target"), ("--quant-shift", "quant_shift"), ("--quant-predict-rows", "quant_predict_rows"), ("--web-search-max-results", "web_search_max_results"), ("--confidence-threshold", "confidence_threshold"), ("--gain-ratio-threshold", "gain_ratio_threshold"), ("--iterations", "iterations")]:
        option(command, flag, payload.get(key))
    option(command, "--quant-models", payload.get("quant_models"), True)
    for flag, key in [("--higher-timeframes", "higher_timeframes"), ("--indicators", "indicators"), ("--quant-indicators", "quant_indicators"), ("--web-search-aspects", "web_search_aspects"), ("--web-search-extra-terms", "web_search_extra_terms"), ("--web-search-topics", "web_search_topics")]:
        option(command, flag, payload.get(key), True)
    # custom preferred sites
    option(command, "--web-search-sites", payload.get("web_search_sites"), True)
    option(command, "--model-names", payload.get("model_names"), True)
    option(command, "--prompt-files", payload.get("prompt_files"), True)
    if payload.get("quant_enabled"): command.append("--quant-enabled")
    if payload.get("web_search_enabled"): command.append("--web-search-enabled")
    if payload.get("dry_run"): command.append("--dry-run")
    return command


def build_backtest(payload: dict) -> list[str]:
    command = [sys.executable, "-m", "backtesting.backtest"]
    option(command, "--symbols", payload.get("symbols"), True)
    for flag, key in [("--lookback", "lookback"), ("--interval", "interval"), ("--step", "step"), ("--iterations", "iterations"), ("--n", "n"), ("--max-expected-time", "max_expected_time"), ("--token-limit", "token_limit"), ("--input-token-price", "input_token_price"), ("--output-token-price", "output_token_price"), ("--max-cost", "max_cost"), ("--output-dir", "output_dir"), ("--quant-input-data", "quant_input_data"), ("--quant-model", "quant_model"), ("--quant-transform", "quant_transform"), ("--quant-output-target", "quant_output_target"), ("--quant-shift", "quant_shift"), ("--quant-predict-rows", "quant_predict_rows"), ("--quant-target-mode", "quant_target_mode"), ("--quant-direction-threshold", "quant_direction_threshold"), ("--web-search-max-results", "web_search_max_results")]:
        option(command, flag, payload.get(key))
    option(command, "--quant-models", payload.get("quant_models"), True)
    for flag, key in [("--higher-timeframes", "higher_timeframes"), ("--indicators", "indicators"), ("--quant-indicators", "quant_indicators"), ("--web-search-aspects", "web_search_aspects"), ("--web-search-extra-terms", "web_search_extra_terms"), ("--web-search-topics", "web_search_topics")]:
        option(command, flag, payload.get(key), True)
    option(command, "--prompt-files", payload.get("prompt_files"), True)
    option(command, "--web-search-sites", payload.get("web_search_sites"), True)
    option(command, "--model-names", payload.get("model_names"), True)
    if payload.get("quant_enabled"): command.append("--quant-enabled")
    if payload.get("web_search_enabled"): command.append("--web-search-enabled")
    return command


def launch(payload: dict, mode: str):
    with LOCK:
        active = RUN.get("process")
        if active and active.poll() is None:
            return False, "A task is already running. Stop it before starting another."
        if not words(payload.get("symbols")):
            return False, "At least one symbol is required."
        validation_error = validate_run_payload(payload, mode)
        if validation_error:
            return False, validation_error
        command = build_backtest(payload) if mode == "backtest" else build_live(payload)
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            process = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, encoding="utf-8", errors="replace")
        except (OSError, ValueError) as exc:
            RUN.update({"mode": mode, "status": "Launch error", "error": str(exc), "output": [f"[dashboard] {exc}"]})
            return False, f"Could not launch: {exc}"
        set_stop_request(False, mode)
        RUN.update({
            "process": process,
            "mode": mode,
            "status": "Running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "command": command,
            "output": ["$ " + " ".join(command)],
            "error": None,
            "exit_code": None,
            "progress": {"current": 0, "total": 0, "percent": 0.0},
            "symbol_progress": {},
            "total_progress_seen": False,
        })
        threading.Thread(target=consume, args=(process,), daemon=True).start()
    return True, f"{mode.title()} started. Follow every step in the execution console."


def live_backtest_metrics(output: list[str]) -> dict:
    """Summarize completed backtest trade lines while the process is still running."""
    outcomes, returns, confidences = [], [], []
    agreement = {"agreed_windows": 0, "disagreed_windows": 0, "no_trade_windows": 0}
    for line in output:
        match = re.search(r"Confidence:\s*([\d.]+)\s*\|\s*Outcome:\s*(success|failure|timeout)\s*\|\s*Return:\s*(-?[\d.]+)%", line, re.I)
        if match:
            confidences.append(float(match.group(1)))
            outcomes.append(match.group(2).lower())
            returns.append(float(match.group(3)))
        consensus = re.search(r"\[consensus\].*status=(agree|disagree|no_trade)", line, re.I)
        if consensus:
            status = consensus.group(1).lower()
            agreement[{"agree": "agreed_windows", "disagree": "disagreed_windows", "no_trade": "no_trade_windows"}[status]] += 1
    total = len(outcomes)
    wins = outcomes.count("success")
    cumulative = peak = drawdown = 0.0
    for value in returns:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    directional = agreement["agreed_windows"] + agreement["disagreed_windows"]
    completed = [index for index, outcome in enumerate(outcomes) if outcome in {"success", "failure"}]
    calibration_errors = [
        abs((confidences[index] / 100 if confidences[index] > 1 else confidences[index]) - (1.0 if outcomes[index] == "success" else 0.0))
        for index in completed
    ]
    return {
        "trades": total,
        "wins": wins,
        "win_rate": wins / total if total else 0.0,
        "total_return": sum(returns),
        "max_drawdown": drawdown,
        "llm_consensus": {**agreement, "agreement_ratio": agreement["agreed_windows"] / directional if directional else 0.0},
        "llm_performance": {
            "agreement_ratio": agreement["agreed_windows"] / directional if directional else 0.0,
            "direction_accuracy": wins / len(completed) if completed else 0.0,
            "confidence_calibration_error": sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0,
            "decision_stability": 0.0,
        },
    }


def _normalize_dashboard_candle(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _build_live_symbol_payload(symbol: str, interval: str | None = None) -> dict:
    interval = interval or DASHBOARD_LIVE_INTERVAL
    original_symbol = CryptoConfig.SYMBOL
    original_interval = CryptoConfig.INTERVAL
    try:
        CryptoConfig.SYMBOL = symbol
        CryptoConfig.INTERVAL = interval
        candles_df = get_candles()
        indicator_df = calculate_indicators(candles_df, DEFAULT_INDICATORS)
        merged_df = candles_df.copy().join(indicator_df)
        candles = []
        for row in merged_df.to_dict(orient="records"):
            candles.append({key: _normalize_dashboard_candle(value) for key, value in row.items()})
        snapshot = get_market_snapshot(candles_df)
        latest = candles[-1] if candles else {}
        price = snapshot.get("price") if snapshot else latest.get("close")
        return {
            "symbol": symbol,
            "time_frame": interval,
            "candles": candles,
            "market": {
                "symbol": symbol,
                "current_time_frame": interval,
                "current_price": price,
                "price": price,
            },
            "snapshot": snapshot,
            "latest": latest,
        }
    except Exception as exc:
        print(f"Unable to load live market data for {symbol}: {exc}")
        return {
            "symbol": symbol,
            "time_frame": interval,
            "candles": [],
            "market": {
                "symbol": symbol,
                "current_time_frame": interval,
                "current_price": None,
                "price": None,
            },
            "snapshot": {},
            "latest": {},
        }
    finally:
        CryptoConfig.SYMBOL = original_symbol
        CryptoConfig.INTERVAL = original_interval


def _refresh_web_context(symbol: str) -> dict:
    return search_web_context(
        symbol,
        aspects=["news", "policy", "macro", "exchange"],
        max_results=5,
        enrich_results=True,
    )


def has_telegram_config() -> bool:
    values = read_env_values()
    return bool((values.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")) and (values.get("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")))


def extract_telegram_message(output: list[str]) -> dict:
    for line in reversed(output or []):
        if not isinstance(line, str):
            continue
        match = re.search(r"\[TELEGRAM_MESSAGE\]\s*(\{.*\})", line, re.I | re.S)
        if not match:
            continue
        candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            try:
                parsed = json.loads(candidate.replace('\n', '\\n'))
            except (TypeError, ValueError):
                continue
        if not isinstance(parsed, dict):
            continue
        status = str(parsed.get("status") or "unknown").lower()
        message = parsed.get("message") or ""
        dry_run = bool(parsed.get("dry_run") or status == "dry_run")
        return {
            "status": status,
            "dry_run": dry_run,
            "configured": has_telegram_config(),
            "message": str(message),
        }
    if has_telegram_config():
        return {"status": "idle", "dry_run": False, "configured": True, "message": "No confident trade analysis has been generated yet."}
    return {"status": "not_configured", "dry_run": False, "configured": False, "message": "Trade analysis preview is not available yet."}


def dashboard_data(selected_symbol: str | None = None, refresh: bool = False):
    request = read_json(ROOT / "cache" / "request.json")
    payload = request.get("llm_payload", request)
    market, prices = payload.get("market", {}), payload.get("price_history", [])
    latest = prices[0] if prices else {}
    with LOCK:
        run = {key: value for key, value in RUN.items() if key != "process"}
    telegram = extract_telegram_message(run.get("output", []))
    backtest = read_json(ROOT / "backtest_results" / "summary.json", {})
    if str(run.get("mode", "")).lower() == "backtest" and run.get("status") in {"Running", "Stopping"}:
        # Do not expose a previous run while the current backtest is still running.
        backtest = {}
    detail_symbol = next(iter(backtest.get("symbols", {})), "")
    backtest_details = read_json(ROOT / "backtest_results" / f"{detail_symbol}_results.json", []) if detail_symbol else []
    discovered_symbols = [item for item in [request.get("symbol"), market.get("symbol"), *DEFAULT_SYMBOLS, *[path.stem.removeprefix("crypto_") for path in (ROOT / "cache").glob("crypto_*.json") if path.is_file()]] if item]
    available_symbols = sorted({symbol for symbol in discovered_symbols if symbol})
    symbol = selected_symbol or market.get("symbol") or request.get("symbol") or "-"
    cache_path = ROOT / "cache" / f"crypto_{symbol}.json"
    cache_payload = read_json(cache_path, {}) if cache_path.exists() else {}
    symbol_is_configured = bool(symbol and symbol != "-")
    use_live_payload = symbol_is_configured and (refresh or not cache_payload)
    if cache_payload:
        cached_candles = cache_payload.get("candles") or []
        if not any(candle.get("rsi") is not None for candle in cached_candles[-3:]):
            use_live_payload = symbol_is_configured
    live_payload = None
    live_future = None
    news_future = None
    if use_live_payload:
        live_future = DATA_REFRESH_EXECUTOR.submit(_build_live_symbol_payload, symbol, DASHBOARD_LIVE_INTERVAL)
    if refresh and symbol_is_configured:
        news_future = DATA_REFRESH_EXECUTOR.submit(_refresh_web_context, symbol)
    if live_future:
        live_payload = live_future.result()
    if live_payload and live_payload.get("candles"):
        candles = live_payload.get("candles", [])
        latest = live_payload.get("latest", {})
        market_price = live_payload.get("market", {}).get("current_price")
        market = {
            "symbol": live_payload.get("symbol", symbol),
            "current_time_frame": live_payload.get("time_frame", DASHBOARD_LIVE_INTERVAL),
            "current_price": market_price,
            **live_payload.get("market", {}),
        }
        prices = candles
        if candles:
            latest = live_payload.get("latest", {})
            market.update({
                "rsi": latest.get("rsi"),
                "macd": latest.get("macd_hist"),
            })
        cache_payload = {
            "symbol": symbol,
            "time_frame": live_payload.get("time_frame", DASHBOARD_LIVE_INTERVAL),
            "candles": candles,
            "market": live_payload.get("market", {}),
            "current_price": market_price,
        }
        try:
            cache_path.write_text(json.dumps(cache_payload, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            print(f"Could not persist cache for {symbol}: {exc}")
    elif cache_payload:
        cache_symbol = cache_payload.get("symbol") or symbol
        cache_time_frame = cache_payload.get("time_frame") or cache_payload.get("interval") or market.get("current_time_frame") or request.get("time_frame") or "-"
        candles = cache_payload.get("candles") or []
        latest = candles[-1] if candles else latest
        market_price = latest.get("close") if latest else None
        if cache_payload.get("current_price") is not None:
            market_price = cache_payload.get("current_price")
        if cache_payload.get("price") is not None:
            market_price = cache_payload.get("price")
        market = {
            "symbol": cache_symbol,
            "current_time_frame": cache_time_frame,
            "current_price": market_price,
            **(cache_payload.get("market") or {})
        }
        prices = candles
        if candles:
            latest = candles[-1] if candles else latest
            market.update({
                "rsi": latest.get("rsi"),
                "macd": latest.get("macd_hist"),
            })
    else:
        market = {**market, "symbol": symbol}
    # Refresh news only for explicit dashboard refreshes; passive polling uses the latest saved context.
    web_ctx = payload.get("web_context", {}) or {}
    web_context_path = ROOT / "cache" / f"web_{symbol}.json"
    if refresh and symbol_is_configured:
        web_ctx = news_future.result() if news_future else _refresh_web_context(symbol)
        try:
            web_context_path.write_text(json.dumps(web_ctx, indent=2, default=str), encoding="utf-8")
        except OSError as exc:
            print(f"Could not persist web context for {symbol}: {exc}")
    elif web_context_path.exists():
        web_ctx = read_json(web_context_path, {})
    web_context_text = web_ctx.get("context", "")
    web_search_unavailable = isinstance(web_context_text, str) and web_context_text.lower().startswith("web search unavailable")
    quant_payload = payload.get("quant", {})
    quant_path = ROOT / "cache" / f"quant_{symbol}.json"
    if quant_path.exists():
        quant_payload = read_json(quant_path, {})
    response = {
        "run": run,
        "run_metrics": live_backtest_metrics(run.get("output", [])),
        "telegram": telegram,
        "market": {
            "symbol": market.get("symbol", request.get("symbol", "-")),
            "interval": market.get("current_time_frame", market.get("interval", request.get("time_frame", "-"))),
            "price": market.get("current_price", market.get("price", latest.get("close"))),
            "updated_at": latest.get("time"),
            "rsi": market.get("rsi", latest.get("rsi")),
            "macd": market.get("macd", latest.get("macd_hist")),
            "candles": list(reversed(prices[:80]))
        },
        "available_symbols": available_symbols,
        "quant": quant_payload,
        "news": web_ctx.get("results", []),
        "web_search_unavailable": web_search_unavailable,
        "web_search_context": web_context_text,
        "backtest": backtest,
        "backtest_details": backtest_details,
    }
    return response


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)
    def send_json(self, value, status=200):
        body = json.dumps(safe_json_value(value), default=str, allow_nan=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ml-data":
            # simple pagination via querystring not required currently
            params = {k: v[0] for k, v in (dict((p.split('=') for p in (urlparse(self.path).query or '').split('&') if p)) ).items()} if urlparse(self.path).query else {}
            limit = int(params.get('limit', 100)) if params.get('limit') else 100
            return self.send_json(list_records(limit=limit))
        if path == "/api/ml-data/export":
            records = export_records()
            return self.send_json({'records': records})
        if path == "/api/dashboard":
            params = parse_qs(urlparse(self.path).query)
            selected_symbol = params.get("symbol", [""])[0]
            refresh = params.get("refresh", ["0"])[0].lower() in ("1", "true", "yes")
            return self.send_json(dashboard_data(selected_symbol or None, refresh=refresh))
        if path == "/api/prompt-files":
            names = list_prompt_files()
            return self.send_json({"files": names})
        if path == "/api/prompt-file":
            params = parse_qs(urlparse(self.path).query)
            name = params.get("name", [""])[0]
            content = read_prompt_file(name)
            if content is None:
                return self.send_json({"ok": False, "message": "Prompt file not found."}, 404)
            return self.send_json({"ok": True, "name": safe_prompt_name(name), "content": content})
        if path == "/api/defaults":
            # Provide GUI with runtime defaults from config and sensible main defaults
            return self.send_json({
                "symbols": DEFAULT_SYMBOLS,
                "interval": DEFAULT_INTERVAL,
                "limit": DEFAULT_LIMIT,
                "lookback": DEFAULT_LIMIT,
                "step": 10,
                "iterations": 2,
                "higher_timeframes": DEFAULT_HIGHER_TIMEFRAMES,
                "indicators": DEFAULT_INDICATORS,
                "n": DEFAULT_N,
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "gain_ratio_threshold": GAIN_RATIO_THRESHOLD,
                "model_names": [MODEL_NAME],
                "prompt_files": [],
                "quant_limit": DEFAULT_LIMIT,
                "quant_test_size": 0.2,
                "quant_input_data": "both",
                "quant_input_set": "both",
                "quant_indicators": [],
                "quant_model": "random_forest",
                "quant_models": ["random_forest"],
                "quant_target_mode": "raw_price",
                "quant_direction_threshold": 0.001,
                "quant_transform": "none",
                "quant_output_target": "close",
                "quant_shift": 1,
                "quant_predict_rows": 1,
                "quant_enabled": False,
                "web_search_enabled": False,
                "web_search_aspects": ["policy", "news", "macro", "exchange"],
                "web_search_extra_terms": [],
                "web_search_sites": [],
                "web_search_topics": [],
                "web_search_max_results": 5,
                "max_expected_time": 12,
                "token_limit": 1500000,
                "input_token_price": 0.0,
                "output_token_price": 0.0,
                "max_cost": 1.0,
                "output_dir": "backtest_results",
            })
        if path == "/api/settings":
            values = read_env_values()
            return self.send_json({
                "openrouter_api_key": values.get("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", "")),
                "telegram_bot_token": values.get("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "")),
                "telegram_chat_id": values.get("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", "")),
            })
        if path == "/api/saved-configs":
            return self.send_json({"configs": read_saved_configs()})
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        if path in {"/dashboard", "/dashboard/"}:
            self.path = "/"
        elif path.startswith("/dashboard/"):
            self.path = path.removeprefix("/dashboard")
        return super().do_GET()
    def do_POST(self):
        try: payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        except (ValueError, json.JSONDecodeError): return self.send_json({"ok": False, "message": "Invalid JSON request."}, 400)
        path = urlparse(self.path).path
        if path in {"/api/run", "/api/run/live", "/api/run/test"}:
            mode = "backtest" if path.endswith("test") or payload.get("mode") == "backtest" else "live"
            ok, message = launch(payload, mode)
            return self.send_json({"ok": ok, "message": message}, 200 if ok else 409)
        if path == "/api/ml-data":
            try:
                rec = append_record(payload)
                return self.send_json({"ok": True, "record": rec})
            except Exception as exc:
                return self.send_json({"ok": False, "message": str(exc)}, 500)
        if path == "/api/ml-data/update":
            rid = payload.get('id')
            if not rid:
                return self.send_json({"ok": False, "message": "id required"}, 400)
            rec = update_record(rid, payload.get('updates', {}))
            if rec:
                return self.send_json({"ok": True, "record": rec})
            return self.send_json({"ok": False, "message": "record not found"}, 404)
        if path == "/api/stop":
            ok, message = stop_active_process()
            status = 200 if ok else 409
            return self.send_json({"ok": ok, "message": message}, status)
        if path == "/api/settings":
            save_env_values({
                "OPENROUTER_API_KEY": str(payload.get("openrouter_api_key", "")).strip(),
                "TELEGRAM_BOT_TOKEN": str(payload.get("telegram_bot_token", "")).strip(),
                "TELEGRAM_CHAT_ID": str(payload.get("telegram_chat_id", "")).strip(),
            })
            return self.send_json({"ok": True, "message": "Settings saved. Restart running analysis tasks to use new values."})
        if path == "/api/saved-configs":
            configs = payload.get("configs", payload)
            if not isinstance(configs, list):
                return self.send_json({"ok": False, "message": "Saved configs payload must be a list."}, 400)
            stored = write_saved_configs(configs)
            return self.send_json({"ok": True, "configs": stored, "message": "Saved configs persisted."})
        if path == "/api/prompt-files":
            name = str(payload.get("name", "")).strip()
            content = str(payload.get("content", ""))
            if not name:
                return self.send_json({"ok": False, "message": "Prompt file name is required."}, 400)
            try:
                saved_name = write_prompt_file(name, content)
                return self.send_json({"ok": True, "name": saved_name})
            except ValueError as exc:
                return self.send_json({"ok": False, "message": str(exc)}, 400)
        return self.send_json({"ok": False, "message": "Endpoint not found."}, 404)


if __name__ == "__main__":
    print("Trading command center: http://localhost:8080")
    ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
