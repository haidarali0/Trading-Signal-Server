import argparse
import csv
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import (
    CONFIDENCE_THRESHOLD,
    DEFAULT_HIGHER_TIMEFRAMES,
    DEFAULT_INDICATORS,
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_N,
    DEFAULT_SYMBOLS,
    GAIN_RATIO_THRESHOLD,
    MODEL_NAME,
)
from crypto_data.getter import Config, get_candles, get_market_snapshot
from crypto_data.indicators import calculate_indicators
from engine.llm import build_llm_market_input, inference, load_prompt_texts, select_prompt_text
from engine.plot import plot_data
from helper.utils import calculate_ratios, format_minimal_pro, send_telegram_message
from ml_builder import append_record
from quant import (
    available_models,
    available_transform_modes,
    explain_quant_output,
    prepare_quant_dataset,
    predict_with_model,
    train_regressor,
    QuantConfig,
    run_quant_models,
    available_target_modes,
    available_classifiers,
)
from web.search import search_web_context


LIVE_PENDING_FILE = os.path.join("cache", "pending_live_signals.json")
STOP_REQUEST_FILE = os.path.join("cache", "stop_requested.json")


def stop_requested() -> bool:
    try:
        if not os.path.exists(STOP_REQUEST_FILE):
            return False
        with open(STOP_REQUEST_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return bool(payload.get("active"))
    except (OSError, ValueError, TypeError):
        return False


# Function: parse_arguments
def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for the trading analysis system."""
    parser = argparse.ArgumentParser(
        description="Trading View Analysis System - Analyze cryptocurrency markets using LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # Run with default symbols
  python main.py -s BTCUSDT ETHUSDT                 # Analyze specific symbols
  python main.py --interval 4h --limit 500          # Custom timeframe and data limit
  python main.py --dry-run                          # Test without sending Telegram messages
        """,
    )

    parser.add_argument(
        "-s",
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help=f"Symbols to analyze (default: {DEFAULT_SYMBOLS})",
    )
    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL,
        help=f"Main timeframe interval (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--model-names",
        nargs="+",
        default=None,
        help=f"One or more OpenRouter model names used across iterations for voting (default: {MODEL_NAME} from .env)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Number of candles to fetch for the LLM request (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--quant-limit",
        type=int,
        default=None,
        help="Number of candles to use for quant dataset preparation (default: same as --limit)",
    )
    parser.add_argument(
        "--quant-input-data",
        choices=["ohlcv", "indicators", "both"],
        default="both",
        help="Quant input data to use as model features (ohlcv, indicators, or both)",
    )
    parser.add_argument(
        "--quant-test-size",
        type=float,
        default=0.2,
        help="Fraction of the quant dataset to use for testing",
    )
    parser.add_argument(
        "--higher-timeframes",
        nargs="+",
        default=DEFAULT_HIGHER_TIMEFRAMES,
        help=f"Higher timeframe intervals (default: {DEFAULT_HIGHER_TIMEFRAMES})",
    )
    parser.add_argument(
        "--indicators",
        nargs="+",
        default=DEFAULT_INDICATORS,
        help=f"Indicator columns to include for the LLM context (default: {DEFAULT_INDICATORS})",
    )
    parser.add_argument(
        "--quant-indicators",
        nargs="+",
        default=None,
        help="Optional list of specific indicator names to use when --quant-input-set is indicators or both",
    )
    parser.add_argument(
        "--quant-enabled",
        action="store_true",
        help="Enable quant model training and include quant output in LLM context",
    )
    parser.add_argument(
        "--quant-target-mode",
        choices=available_target_modes(),
        default="raw_price",
        help="Target to predict: raw_price, percentage_return, log_return, binary_direction, ternary_direction, or future_volatility",
    )
    parser.add_argument(
        "--quant-models",
        nargs="+",
        default=None,
        help="One or more quant model names to run in parallel; --quant-model remains supported",
    )
    parser.add_argument(
        "--quant-direction-threshold",
        type=float,
        default=0.001,
        help="Minimum forward return used to classify up/down movement",
    )
    parser.add_argument(
        "--quant-model",
        choices=sorted(set(available_models()) | set(available_classifiers())),
        default="random_forest",
        help="Sklearn regressor model to train for quant signals",
    )
    parser.add_argument(
        "--quant-input-set",
        choices=["ohlcv", "indicators", "both"],
        default="both",
        help="Use candle OHLCV, indicators, or both as features for the quant model",
    )
    parser.add_argument(
        "--quant-transform",
        choices=available_transform_modes(),
        default="none",
        help="Dataset transformation used before quant model training (none, bins, average, log)",
    )
    parser.add_argument(
        "--quant-output-target",
        default="close",
        help="Quant output target column for training (default: close)",
    )
    parser.add_argument(
        "--quant-shift",
        type=int,
        default=1,
        help="Number of rows to shift the target value for quant model training (default: 1)",
    )
    parser.add_argument(
        "--quant-predict-rows",
        type=int,
        default=1,
        help="Number of final rows to predict and include in quant output",
    )
    parser.add_argument(
        "--web-search-enabled",
        action="store_true",
        help="Fetch web context for each symbol and include it in the LLM prompt",
    )
    parser.add_argument(
        "--web-search-aspects",
        nargs="+",
        default=["policy", "news", "macro", "exchange"],
        help="Aspect keywords to use when building the web search query for each symbol",
    )
    parser.add_argument(
        "--web-search-extra-terms",
        nargs="+",
        default=[],
        help="Extra keywords to append to the web search query",
    )
    parser.add_argument(
        "--web-search-topics",
        nargs="+",
        default=[],
        help="Web-search topics to target, such as policy, news, updates, or regulation",
    )
    parser.add_argument(
        "--web-search-max-results",
        type=int,
        default=5,
        help="Maximum number of web results to include in the LLM context",
    )
    parser.add_argument(
        "--web-search-sites",
        nargs="+",
        default=None,
        help="Optional list of preferred domains to prioritize during web search (e.g. coindesk.com)",
    )
    parser.add_argument(
        "--prompt-files",
        nargs="+",
        default=None,
        help="One or more prompt file paths. If one file is provided, all models use it. If multiple files are provided, each model uses the corresponding file.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=CONFIDENCE_THRESHOLD,
        help=f"Minimum confidence threshold for signals (default: {CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument(
        "--gain-ratio-threshold",
        type=float,
        default=GAIN_RATIO_THRESHOLD,
        help=f"Minimum gain ratio threshold (default: {GAIN_RATIO_THRESHOLD})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis without sending Telegram messages",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2,
        help="Number of analysis iterations per symbol (default: 2)",
    )
    args = parser.parse_args()
    validate_arguments(parser, args)
    return args


def validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not (os.getenv("OPENROUTER_API_KEY") or ""):
        parser.error("OPENROUTER_API_KEY is required. Set it in .env or the dashboard Settings tab.")
    if not args.model_names:
        args.model_names = [MODEL_NAME]
    if len(set(args.model_names)) != len(args.model_names):
        parser.error("--model-names must not contain duplicate model names")
    if args.iterations < len(args.model_names):
        parser.error("--iterations must be greater than or equal to the number of --model-names")
    if args.prompt_files and len(args.prompt_files) > args.iterations:
        parser.error("--prompt-files must not specify more files than iterations")
    if not 0 <= args.confidence_threshold <= 1:
        parser.error("--confidence-threshold must be between 0 and 1")
    if args.gain_ratio_threshold < 0:
        parser.error("--gain-ratio-threshold must be greater than or equal to 0")
    if args.iterations < 1:
        parser.error("--iterations must be greater than or equal to 1")
    if args.limit < 1:
        parser.error("--limit must be greater than or equal to 1")
    if args.quant_limit is not None and args.quant_limit < 1:
        parser.error("--quant-limit must be greater than or equal to 1")
    if not 0.01 <= args.quant_test_size <= 0.99:
        parser.error("--quant-test-size must be between 0.01 and 0.99")
    if args.quant_shift < 1:
        parser.error("--quant-shift must be greater than or equal to 1")
    if args.quant_predict_rows < 1:
        parser.error("--quant-predict-rows must be greater than or equal to 1")
    if args.quant_direction_threshold < 0:
        parser.error("--quant-direction-threshold must be greater than or equal to 0")
    if args.web_search_max_results < 1:
        parser.error("--web-search-max-results must be greater than or equal to 1")


def voting_models(args: argparse.Namespace) -> List[str]:
    return args.model_names


def load_prompt_files(args: argparse.Namespace) -> list[str] | None:
    if not args.prompt_files:
        return None
    return [str(path) for path in args.prompt_files]


def winning_response(responses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    scenarios = [str(response.get("scenario", "")).lower().strip() for response in responses]
    vote_counts = Counter(scenarios)
    if not vote_counts:
        return None
    scenario, votes = vote_counts.most_common(1)[0]
    if scenario not in {"up", "down"} or votes <= len(responses) / 2:
        return None
    winners = [response for response in responses if str(response.get("scenario", "")).lower().strip() == scenario]
    return max(winners, key=lambda response: float(response.get("confidence", 0) or 0))


# Function: configure_runtime
def configure_runtime(args: argparse.Namespace, symbol: str) -> str:
    """Apply runtime configuration for a single symbol analysis pass."""
    Config.SYMBOL = symbol
    Config.LIMIT = args.limit
    Config.INTERVAL = args.interval
    Config.HIGHER_TIMEFRAMES = args.higher_timeframes
    return Config.INTERVAL


# Function: prepare_quant_context
def prepare_quant_context(
    args: argparse.Namespace,
    basic_interval: str,
    quant_limit: int,
    quant_data_cached: Optional[Dict[str, Any]],
    quant_prepared: bool,
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[Dict[str, Any]]]:
    """Prepare quant features and predictions when enabled, reusing cached state when possible."""
    if not args.quant_enabled:
        return None, quant_prepared, quant_data_cached

    if quant_prepared and quant_data_cached is not None:
        return quant_data_cached, True, quant_data_cached

    include_ohlcv = args.quant_input_data in ["ohlcv", "both"]
    include_indicators = args.quant_input_data in ["indicators", "both"]
    quant_indicators = args.quant_indicators if args.quant_indicators is not None else None

    target_mode = getattr(args, "quant_target_mode", "raw_price")
    X, y = prepare_quant_dataset(
        interval=basic_interval,
        limit=quant_limit,
        target_column=args.quant_output_target,
        include_ohlcv=include_ohlcv,
        include_indicators=include_indicators,
        indicators_list=quant_indicators if include_indicators else None,
        shift=args.quant_shift,
        transform_mode=args.quant_transform,
        target_mode=target_mode,
        direction_threshold=getattr(args, "quant_direction_threshold", 0.001),
    )

    if not len(X) or not len(y):
        return None, False, None

    try:
        model_names = getattr(args, "quant_models", None) or [args.quant_model]
        family = (
            "classification" if target_mode in {"binary_direction", "ternary_direction"}
            else "volatility" if target_mode == "future_volatility"
            else "regression"
        )
        quant_result = run_quant_models(
            X,
            y,
            QuantConfig(
                target_mode=target_mode,
                horizon=args.quant_shift,
                direction_threshold=getattr(args, "quant_direction_threshold", 0.001),
                model_families={family: model_names},
                test_size=args.quant_test_size,
            ),
            predict_rows=args.quant_predict_rows,
        )
        if not quant_result.get("models"):
            print("Quant dataset empty after dropping NaNs — skipping quant training.")
            return None, False, None
        return quant_result, True, quant_result
    except Exception as exc:
        print(f"Quant preprocessing error: {exc}")
        return None, True, None


# Function: fetch_market_data
def fetch_market_data(args: argparse.Namespace, basic_interval: str) -> Tuple[Any, Any, Any, Dict[str, Dict[str, Any]]]:
    """Fetch candle data, indicators, snapshot data, and higher-timeframe context."""
    df = get_candles()
    indicators = calculate_indicators(df, args.indicators)
    snapshot = get_market_snapshot(df)

    higher_tf_data: Dict[str, Dict[str, Any]] = {}
    original_interval = Config.INTERVAL
    try:
        for tf in Config.HIGHER_TIMEFRAMES:
            Config.INTERVAL = tf
            higher_tf_data[tf] = {"candles": get_candles()}
    finally:
        Config.INTERVAL = original_interval

    return df, indicators, snapshot, higher_tf_data


# Function: fetch_web_context
def fetch_web_context(args: argparse.Namespace, symbol: str) -> Optional[Dict[str, Any]]:
    """Retrieve optional web context for the current symbol and return it as a structured payload."""
    if not args.web_search_enabled:
        return None

    try:
        print(f"[WEB] searching for context for {symbol}...")
        web_context_data = search_web_context(
            symbol,
            aspects=args.web_search_aspects,
            extra_terms=args.web_search_extra_terms + args.web_search_topics,
            max_results=args.web_search_max_results,
            additional_priority_domains=args.web_search_sites,
        )
        if web_context_data:
            print(f"[WEB] context captured for {symbol}")
        return {
            "symbol": symbol,
            "query_topics": args.web_search_aspects + args.web_search_topics,
            "query": web_context_data.get("query", ""),
            "context": web_context_data.get("context", ""),
            "results": web_context_data.get("results", []),
        }
    except Exception as exc:
        return {
            "symbol": symbol,
            "query_topics": args.web_search_aspects + args.web_search_topics,
            "query": "",
            "context": f"Web search unavailable: {exc}",
            "results": [],
        }


def to_jsonable(value: Any) -> Any:
    """Convert common Python and pandas objects into JSON-serializable structures."""
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# Function: persist_analysis_cache
def persist_analysis_cache(
    symbol: str,
    time_frame: str,
    market_info: str,
    payload: Dict[str, Any],
    crypto_data: Optional[Dict[str, Any]],
    quant_data: Optional[Dict[str, Any]],
    web_context: Optional[Dict[str, Any]],
) -> None:
    """Persist the exact LLM request payload alongside cached crypto, quant, and web context."""
    os.makedirs("cache", exist_ok=True)
    cache_entry = {
        "symbol": symbol,
        "time_frame": time_frame,
        "llm_input": market_info,
        "llm_payload": payload,
        "crypto_data": crypto_data or {},
        "quant_data": quant_data,
        "web_data": web_context,
    }
    with open("cache/request.json", "w", encoding="utf-8") as handle:
        json.dump(cache_entry, handle, indent=2)
        print("✔ Request saved to cache/request.json")

    csv_path = "cache/requests.csv"
    fieldnames = [
        "timestamp",
        "symbol",
        "time_frame",
        "llm_input",
        "llm_payload",
        "crypto_data",
        "quant_data",
        "web_data",
    ]
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "time_frame": time_frame,
                "llm_input": market_info,
                "llm_payload": json.dumps(payload, ensure_ascii=False),
                "crypto_data": json.dumps(crypto_data or {}, ensure_ascii=False),
                "quant_data": json.dumps(quant_data, ensure_ascii=False) if quant_data is not None else "",
                "web_data": json.dumps(web_context, ensure_ascii=False) if web_context is not None else "",
            }
        )
    print(f"✔ Request appended to {csv_path}")

    if crypto_data is not None:
        try:
            with open(f"cache/crypto_{symbol}.json", "w", encoding="utf-8") as handle:
                json.dump(crypto_data, handle, indent=2)
                print(f"✔ Crypto data saved to cache/crypto_{symbol}.json")
        except Exception as exc:
            print(f"Could not save crypto cache: {exc}")

    if web_context is not None:
        try:
            with open(f"cache/web_{symbol}.json", "w", encoding="utf-8") as handle:
                json.dump(web_context, handle, indent=2)
                print(f"✔ Web context saved to cache/web_{symbol}.json")
        except Exception as exc:
            print(f"Could not save web context cache: {exc}")

    if quant_data is not None:
        try:
            with open(f"cache/quant_{symbol}.json", "w", encoding="utf-8") as handle:
                json.dump(quant_data, handle, indent=2)
                print(f"✔ Quant data saved to cache/quant_{symbol}.json")
        except Exception as exc:
            print(f"Could not save quant cache: {exc}")


# Function: should_process_signal
def should_process_signal(signal_history: List[str]) -> Tuple[bool, str]:
    """Return whether a signal history is consistent enough for a trade decision."""
    if not signal_history:
        return False, "No signals"
    if len(signal_history) < 2:
        return False, "Not enough signals"
    if any(signal == "no_trade" for signal in signal_history):
        return False, "no_trade present"
    vote_counts = Counter(signal_history)
    scenario, votes = vote_counts.most_common(1)[0]
    if votes > len(signal_history) / 2 and scenario in {"up", "down"}:
        return True, f"Vote passed ({scenario}: {votes}/{len(signal_history)})"
    return False, f"Vote tied or mismatched ({dict(vote_counts)})"


def _load_pending_live_signals() -> List[Dict[str, Any]]:
    try:
        with open(LIVE_PENDING_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_pending_live_signals(records: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(LIVE_PENDING_FILE), exist_ok=True)
    with open(LIVE_PENDING_FILE, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, default=str)


def _automatic_live_result(pending: Dict[str, Any], df: Any) -> Optional[Dict[str, Any]]:
    rows = df.to_dict("records") if hasattr(df, "to_dict") else []
    signal_time = str(pending.get("signal_time", ""))
    signal_index = next((index for index, row in enumerate(rows) if str(row.get("time", "")) == signal_time), None)
    if signal_index is None:
        return None

    expected_time = max(1, int(pending.get("expected_time") or 1))
    future = rows[signal_index + 1:signal_index + 1 + expected_time]
    if len(future) < expected_time:
        return {"discard": True}

    scenario = str(pending.get("predicted_label", "")).lower().strip()
    entry_price = float(pending["entry_price"])
    target_price = float(pending["target_price"])
    stop_loss = float(pending["stop_loss"])
    outcome = "timeout"
    return_pct = 0.0

    for candle in future:
        high = float(candle["high"])
        low = float(candle["low"])
        if scenario == "up":
            if high >= target_price:
                outcome = "success"
                return_pct = (target_price - entry_price) / entry_price * 100
                break
            if low <= stop_loss:
                outcome = "failure"
                return_pct = (stop_loss - entry_price) / entry_price * 100
                break
        elif scenario == "down":
            if low <= target_price:
                outcome = "success"
                return_pct = (entry_price - target_price) / entry_price * 100
                break
            if high >= stop_loss:
                outcome = "failure"
                return_pct = (entry_price - stop_loss) / entry_price * 100
                break
        else:
            outcome = "no_trade"
            break

    if outcome == "success":
        ground_truth = scenario
    elif outcome == "failure":
        ground_truth = "down" if scenario == "up" else "up"
    else:
        ground_truth = "no_trade"
    return {
        "outcome": outcome,
        "return_pct": return_pct,
        "ground_truth": ground_truth,
        "outcome_time": future[-1].get("time"),
    }


def resolve_pending_live_signals(symbol: str, df: Any) -> None:
    pending = _load_pending_live_signals()
    remaining: List[Dict[str, Any]] = []
    for item in pending:
        if item.get("symbol") != symbol:
            remaining.append(item)
            continue
        result = _automatic_live_result(item, df)
        if result is None or result.get("discard"):
            continue
        from ml_builder import update_record as update_ml_record
        update_ml_record(str(item["record_id"]), {
            "outcome": result["outcome"],
            "return_pct": result["return_pct"],
            "ground_truth": result["ground_truth"],
            "outcome_time": result["outcome_time"],
            "auto_labeled": True,
        })
    _save_pending_live_signals(remaining)


# Function: maybe_send_signal
def maybe_send_signal(args: argparse.Namespace, result: Dict[str, Any], symbol: str) -> None:
    """Send a validated signal to Telegram when it meets the configured thresholds."""
    # store signal for ML dataset (live mode) before deciding to send
    try:
        # include the full LLM input payload under `features` so saved ML examples
        # contain all inputs used to generate the prediction
        try:
            features = json.loads(market_info) if isinstance(market_info, str) else market_info
        except Exception:
            features = None
        record = append_record({
            'mode': 'live',
            'symbol': symbol,
            'timestamp': result.get('signal_time') or datetime.now(timezone.utc).isoformat(),
            'predicted_label': result.get('scenario'),
            'confidence': result.get('confidence'),
            'entry_price': result.get('entry_price'),
            'target_price': result.get('target_price'),
            'stop_loss': result.get('stop_loss'),
            'expected_time': result.get('expected_time'),
            'analysis': result.get('analysis'),
            'model_name': result.get('model_name'),
            'features': features,
        })
        pending = _load_pending_live_signals()
        if not any(str(item.get("record_id")) == str(record.get("id")) for item in pending):
            pending.append({
                "record_id": record["id"],
                "symbol": symbol,
                "signal_time": record["timestamp"],
                "predicted_label": record.get("predicted_label"),
                "entry_price": record.get("entry_price"),
                "target_price": record.get("target_price"),
                "stop_loss": record.get("stop_loss"),
                "expected_time": record.get("expected_time"),
            })
            _save_pending_live_signals(pending)
    except Exception:
        pass

    if result["confidence"] >= args.confidence_threshold and result["gain_ratio"] >= args.gain_ratio_threshold:
        result["Symbol"] = symbol
        message = format_minimal_pro(result)
        if args.dry_run:
            print("📋 DRY RUN: Would send signal to Telegram")
            print(json.dumps({"status": "dry_run", "dry_run": True, "message": message}, ensure_ascii=False))
            print(f"[TELEGRAM_MESSAGE] {json.dumps({'status': 'dry_run', 'dry_run': True, 'message': message}, ensure_ascii=False)}")
            return

        send_telegram_message(message)
        print(json.dumps({"status": "sent", "dry_run": False, "message": message}, ensure_ascii=False))
        print(f"[TELEGRAM_MESSAGE] {json.dumps({'status': 'sent', 'dry_run': False, 'message': message}, ensure_ascii=False)}")
        print("📤 Signal sent to Telegram!")
        return

    print("📊 Signal below thresholds:")
    print(result)


# ============================
# MAIN LOOP
# ============================
# Function: run_analysis_cycle
def run_analysis_cycle(symbols: List[str], args: argparse.Namespace) -> None:
    """Run the analysis loop for each requested symbol and publish signals when conditions are met."""
    signal_history = {symbol: [] for symbol in symbols}

    prompt_files = load_prompt_files(args)
    prompt_texts = None
    if prompt_files:
        prompt_texts = load_prompt_texts(prompt_files)

    try:
        for symbol in symbols:
            if stop_requested():
                print("[stop] Stop requested before next symbol loop; exiting live analysis.")
                return
            quant_data_cached: Optional[Dict[str, Any]] = None
            quant_prepared = False

            models = voting_models(args)
            responses: List[Dict[str, Any]] = []
            for iteration_index in range(args.iterations):
                if stop_requested():
                    print("[stop] Stop requested before next iteration; exiting live analysis.")
                    return
                print("====================================")
                print(f"Analyzing {symbol}")
                configure_runtime(args, symbol)
                basic_interval = Config.INTERVAL
                quant_limit = args.quant_limit if args.quant_limit is not None else args.limit

                df, indicators, snapshot, higher_tf_data = fetch_market_data(args, basic_interval)
                resolve_pending_live_signals(symbol, df)
                quant_data, quant_prepared, quant_data_cached = prepare_quant_context(
                    args,
                    basic_interval,
                    quant_limit,
                    quant_data_cached,
                    quant_prepared,
                )

                if quant_data is not None:
                    print(f"[LLM] preparing prompt with quant context for {Config.SYMBOL}")
                else:
                    print(f"[LLM] preparing prompt without quant context for {Config.SYMBOL}")

                web_context = fetch_web_context(args, symbol)
                market_info = build_llm_market_input(
                    Config.SYMBOL,
                    basic_interval,
                    df,
                    snapshot,
                    n=DEFAULT_N,
                    indicators=indicators,
                    higher_tf=higher_tf_data,
                    quant_data=quant_data,
                    web_data=web_context,
                )

                payload = json.loads(market_info)
                if quant_data is not None:
                    payload["quant"] = quant_data
                if web_context is not None:
                    payload["web_context"] = {
                        "symbol": web_context.get("symbol"),
                        "query_topics": web_context.get("query_topics", []),
                        "query": web_context.get("query", ""),
                        "context": web_context.get("context", ""),
                        "results": web_context.get("results", []),
                    }
                crypto_data = {
                    "symbol": symbol,
                    "time_frame": basic_interval,
                    "candles": to_jsonable(df),
                    "indicators": to_jsonable(indicators),
                    "snapshot": to_jsonable(snapshot),
                    "higher_timeframes": {
                        tf: {"candles": to_jsonable(data.get("candles", []))}
                        for tf, data in higher_tf_data.items()
                    },
                }
                persist_analysis_cache(symbol, basic_interval, market_info, payload, crypto_data, quant_data, web_context)

                selected_model = models[iteration_index % len(models)]
                prompt_text = None
                if prompt_texts is not None:
                    prompt_text = select_prompt_text(prompt_texts, iteration_index % len(models))
                res, _usage = inference(
                    market_info,
                    Config.SYMBOL,
                    basic_interval,
                    web_context=web_context.get("context", "") if web_context is not None else None,
                    model_name=selected_model,
                    prompt_text=prompt_text,
                )
                res["model_name"] = selected_model
                responses.append(res)
                signal_history[symbol].append(res["scenario"].lower().strip())
                print(f"LLM response for {Config.SYMBOL}: {res}")

                can_process, reason = should_process_signal(signal_history[symbol])
                if not can_process:
                    print(f"{reason} for {Config.SYMBOL}, skipping...")
                    continue

                res = winning_response(responses) or res
                print(f"Vote signals {signal_history[symbol]} for {Config.SYMBOL}, proceeding...")
                plot_data(res["target_price"], res["stop_loss"], res["expected_time"], basic_interval, symbol)
                print("✔ Chart image saved!")

                try:
                    res |= calculate_ratios(res)
                except ValueError as exc:
                    print("===========================")
                    print(exc)
                    continue

                if hasattr(df, "iloc") and len(df):
                    res["signal_time"] = str(df.iloc[-1].get("time", ""))
                maybe_send_signal(args, res, symbol)
    except Exception as exc:
        print(f"error {exc}")


# Function: run_analysis
def run_analysis(symbols: List[str], args: argparse.Namespace) -> None:
    """Repeat live analysis cycles until the dashboard stops the process."""
    while not stop_requested():
        run_analysis_cycle(symbols, args)
        if stop_requested():
            print("[stop] Stop requested, ending live analysis loop.")
            break


if __name__ == "__main__":
    args = parse_arguments()

    print("🚀 Starting Trading View Analysis System")
    print(f"📊 Symbols: {args.symbols}")
    print(f"⏰ Interval: {args.interval}")
    print(f"🤖 Models: {', '.join(args.model_names)}")
    print(f"📈 LLM limit: {args.limit}")
    print(f"📉 Quant limit: {args.quant_limit if args.quant_limit is not None else args.limit}")
    print(f"🧾 LLM indicators: {args.indicators}")
    if args.quant_indicators is not None:
        print(f"🧪 Quant indicators: {args.quant_indicators}")
    else:
        print("🧪 Quant indicators: default/all available")
    print(f"🔄 Iterations: {args.iterations}")
    if args.dry_run:
        print("🔍 DRY RUN MODE - No Telegram messages will be sent")
    print("=" * 50)
    run_analysis(args.symbols, args)
