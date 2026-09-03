import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import pandas as pd

from config import (
    DEFAULT_HIGHER_TIMEFRAMES,
    DEFAULT_INDICATORS,
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_N,
    DEFAULT_SYMBOLS,
    MODEL_NAME,
)
from crypto_data.getter import Config, get_candles, get_market_snapshot
from crypto_data.indicators import calculate_indicators
from engine.llm import build_llm_market_input, inference, load_prompt_texts, select_prompt_text
from quant import prepare_quant_dataset, train_regressor, predict_with_model, explain_quant_output, QuantConfig, run_quant_models, available_target_modes, available_models, available_classifiers
from web.search import search_web_context
from ml_builder import append_record


# Function: evaluate_trade_outcome
def evaluate_trade_outcome(df_future: pd.DataFrame, scenario: str, entry_price: float, target_price: float, stop_loss: float) -> tuple[str, float]:
    """
    Evaluate if the trade was successful based on future price action.
    Returns: (outcome, return_percentage)
    """
    if scenario == "up":
        # For up trade, success if high >= target, failure if low <= stop
        max_high = df_future['high'].max()
        min_low = df_future['low'].min()
        if max_high >= target_price:
            return_percentage = (target_price - entry_price) / entry_price * 100
            return 'success', return_percentage
        elif min_low <= stop_loss:
            return_percentage = (stop_loss - entry_price) / entry_price * 100
            return 'failure', return_percentage
        else:
            return 'timeout', 0.0
    elif scenario == "down":
        # For down trade, success if low <= target, failure if high >= stop
        max_high = df_future['high'].max()
        min_low = df_future['low'].min()
        if min_low <= target_price:
            return_percentage = (entry_price - target_price) / entry_price * 100  # Profit when price goes down
            return 'success', return_percentage
        elif max_high >= stop_loss:
            return_percentage = (entry_price - stop_loss) / entry_price * 100  # Loss when price goes up
            return 'failure', return_percentage
        else:
            return 'timeout', 0.0
    else:
        return 'no_trade', 0.0


def compute_business_metrics(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute business-style metrics from completed trades."""
    if not trades:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "average_trade_duration": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
        }

    wins = [trade["return_pct"] for trade in trades if trade.get("outcome") == "success"]
    losses = [trade["return_pct"] for trade in trades if trade.get("outcome") == "failure"]
    durations = [float(trade.get("expected_time", 0) or 0) for trade in trades]
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    running_returns: List[float] = []

    for trade in trades:
        if trade.get("outcome") == "success":
            cumulative += float(trade.get("return_pct", 0.0) or 0.0)
        elif trade.get("outcome") == "failure":
            cumulative += float(trade.get("return_pct", 0.0) or 0.0)
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)
        running_returns.append(cumulative)

    total_positive = sum(abs(value) for value in wins if value > 0)
    total_negative = sum(abs(value) for value in losses if value < 0)

    return {
        "win_rate": len(wins) / len(trades),
        "profit_factor": (total_positive / total_negative) if total_negative else float("inf" if total_positive else 0.0),
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "average_trade_duration": sum(durations) / len(durations) if durations else 0.0,
        "max_drawdown": max_drawdown,
        "total_return": cumulative,
    }


def _normalized_confidence(value: Any) -> float:
    confidence = float(value or 0.0)
    return confidence / 100 if confidence > 1 else confidence


def compute_llm_performance_metrics(windows: List[Dict[str, Any]], iterations: int) -> Dict[str, float]:
    """Compute repeatability and outcome quality metrics for LLM backtest windows."""
    total_windows = len(windows)
    if not total_windows:
        return {
            "agreement_ratio": 0.0,
            "direction_accuracy": 0.0,
            "confidence_calibration_error": 0.0,
            "decision_stability": 0.0,
        }

    agreed = [window for window in windows if window.get("status") == "agree"]
    disagreements = [window for window in windows if window.get("status") == "disagree"]
    agreement_ratio = 1.0 if iterations <= 1 else len(agreed) / (len(agreed) + len(disagreements)) if agreed or disagreements else 0.0

    completed = [window for window in agreed if window.get("outcome") in {"success", "failure"}]
    direction_accuracy = (
        sum(1 for window in completed if window.get("outcome") == "success") / len(completed)
        if completed else 0.0
    )

    confidence_errors = [
        abs(_normalized_confidence(window.get("confidence")) - (1.0 if window.get("outcome") == "success" else 0.0))
        for window in completed
    ]
    confidence_calibration_error = sum(confidence_errors) / len(confidence_errors) if confidence_errors else 0.0

    variations: List[float] = []
    for window in agreed:
        responses = window.get("responses") or []
        if len(responses) <= 1:
            variations.append(0.0)
            continue
        field_variations = []
        for field in ["confidence", "entry_price", "target_price", "stop_loss", "expected_time"]:
            values = [float(response[field]) for response in responses if response.get(field) not in (None, "")]
            if len(values) <= 1:
                continue
            mean_value = sum(abs(value) for value in values) / len(values)
            if not mean_value:
                continue
            field_variations.append((max(values) - min(values)) / mean_value)
        variations.append(sum(field_variations) / len(field_variations) if field_variations else 0.0)
    average_variation = sum(variations) / len(variations) if variations else 0.0

    return {
        "agreement_ratio": agreement_ratio,
        "direction_accuracy": direction_accuracy,
        "confidence_calibration_error": confidence_calibration_error,
        "decision_stability": max(0.0, 1.0 - min(average_variation, 1.0)),
    }


def winning_llm_response(responses: List[Dict[str, Any]]) -> tuple[Dict[str, Any] | None, str]:
    scenarios = [str(response.get("scenario", "")).lower().strip() for response in responses]
    if "no_trade" in scenarios:
        return None, "no_trade"
    vote_counts = Counter(scenarios)
    if not vote_counts:
        return None, "disagree"
    scenario, votes = vote_counts.most_common(1)[0]
    if scenario not in {"up", "down"} or votes <= len(responses) / 2:
        return None, "disagree"
    winners = [response for response in responses if str(response.get("scenario", "")).lower().strip() == scenario]
    return max(winners, key=lambda response: float(response.get("confidence", 0) or 0)), "agree"


# Function: parse_usage
def parse_usage(usage: Any) -> tuple[int, int, int]:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    if isinstance(usage, dict):
        input_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0)) or 0
        output_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0)) or 0
        total_tokens = usage.get('total_tokens', input_tokens + output_tokens) or (input_tokens + output_tokens)
    else:
        input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', 0)) or 0
        output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', 0)) or 0
        total_tokens = getattr(usage, 'total_tokens', input_tokens + output_tokens) or (input_tokens + output_tokens)

    return input_tokens, output_tokens, total_tokens


# Function: run_backtest
def run_backtest(
    symbols: List[str],
    lookback: int,
    interval: str = DEFAULT_INTERVAL,
    step: int = 10,
    n: int = DEFAULT_N,
    higher_timeframes: List[str] = DEFAULT_HIGHER_TIMEFRAMES,
    indicators: List[str] = DEFAULT_INDICATORS,
    max_expected_time: int = 12,
    token_limit: int = 1500000,
    input_token_price: float = 0.0,
    output_token_price: float = 0.0,
    max_cost: float = 0.0,
    quant_enabled: bool = False,
    quant_input_data: str = "both",
    quant_model: str = "random_forest",
    quant_models: List[str] | None = None,
    quant_target_mode: str = "raw_price",
    quant_direction_threshold: float = 0.001,
    quant_transform: str = "none",
    quant_output_target: str = "close",
    quant_shift: int = 1,
    quant_predict_rows: int = 1,
    web_search_enabled: bool = False,
    web_search_aspects: List[str] | None = None,
    web_search_extra_terms: List[str] | None = None,
    web_search_topics: List[str] | None = None,
    web_search_max_results: int = 5,
    iterations: int = 2,
    model_names: List[str] | None = None,
    prompt_files: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Run backtesting on historical data.
    """
    if model_names is None:
        model_names = [MODEL_NAME]

    prompt_texts = load_prompt_texts(prompt_files) if prompt_files else None
    results = {}
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    total_steps_total = 0
    total_completed_steps = 0
    symbol_steps = []

    for symbol in symbols:
        print(f"\n{'='*50}")
        print(f"Backtesting {symbol}")
        print(f"{'='*50}")

        Config.SYMBOL = symbol
        Config.INTERVAL = interval
        Config.HIGHER_TIMEFRAMES = higher_timeframes

        print(f"[debug] {symbol}: fetching {lookback} {interval} candles", flush=True)
        # Fetch the requested last candles
        df_all = get_candles(interval=interval, limit=lookback)
        if len(df_all) < lookback:
            print(f"⚠️ Requested {lookback} candles but Binance returned {len(df_all)}. Using available data.")
        print(f"Fetched {len(df_all)} candles for {symbol}")
        actual_start = df_all['time'].iloc[0] if len(df_all) else None
        actual_end = df_all['time'].iloc[-1] if len(df_all) else None
        print(f"Actual window: {actual_start} to {actual_end}")

        # Calculate buy and hold return
        if len(df_all) > 0:
            start_price = df_all.iloc[0]['close']
            end_price = df_all.iloc[-1]['close']
            buy_and_hold_return = (end_price - start_price) / start_price * 100
        else:
            buy_and_hold_return = 0.0

        symbol_results = []
        total_return = 0.0
        wins = 0
        losses = 0
        timeouts = 0
        quant_data = None
        agreement_windows = 0
        disagreement_windows = 0
        no_trade_windows = 0
        llm_windows = []

        # Loop through the data
        test_indices = list(range(n, len(df_all) - max_expected_time, step))
        total_steps = len(test_indices)
        symbol_steps.append((symbol, test_indices, total_steps, symbol_results, total_return, wins, losses, timeouts, quant_data, agreement_windows, disagreement_windows, no_trade_windows, llm_windows, buy_and_hold_return, df_all))
        total_steps_total += total_steps
        print(f"[debug] {symbol}: prepared {total_steps} test windows (n={n}, step={step}, future={max_expected_time})", flush=True)

    for symbol, test_indices, total_steps, symbol_results, total_return, wins, losses, timeouts, quant_data, agreement_windows, disagreement_windows, no_trade_windows, llm_windows, buy_and_hold_return, df_all in symbol_steps:
        for completed, i in enumerate(test_indices, start=1):
            total_completed_steps += 1
            print(f"[progress] TOTAL {total_completed_steps}/{total_steps_total}", flush=True)
            print(f"[progress] {symbol} {completed}/{total_steps}", flush=True)
            current_df = df_all.iloc[:i+1]  # Up to current candle
            future_df = df_all.iloc[i+1:i+1+max_expected_time]  # Future candles
            print(f"[debug] step {completed}: candle={df_all.iloc[i]['time']}, history={len(current_df)}, future={len(future_df)}", flush=True)
        
            if len(future_df) < max_expected_time:
                print(f"[debug] step {completed}: insufficient future candles ({len(future_df)} < {max_expected_time}), skipping", flush=True)
                continue

            # Calculate indicators
            indicators_data = calculate_indicators(current_df, indicators)
            snapshot = get_market_snapshot(current_df)
            print(f"[debug] step {completed}: indicators and market snapshot prepared", flush=True)

            # Fetch higher timeframe data
            higher_tf_data = {}
            for tf in higher_timeframes:
                df_tf = get_candles(interval=tf, limit=max(1, n // 2), end_time=df_all.iloc[i]['time'])
                higher_tf_data[tf] = {"candles": df_tf}
            print(f"[debug] step {completed}: higher-timeframe context loaded ({', '.join(higher_timeframes)})", flush=True)

            if quant_enabled:
                print(f"[debug] step {completed}: training quant model {quant_model}", flush=True)
                include_ohlcv = quant_input_data in ["ohlcv", "both"]
                include_indicators = quant_input_data in ["indicators", "both"]
                try:
                    X, y = prepare_quant_dataset(
                        interval=interval,
                        limit=max(lookback, len(current_df)),
                        target_column=quant_output_target,
                        include_ohlcv=include_ohlcv,
                        include_indicators=include_indicators,
                        indicators_list=indicators if include_indicators else None,
                        shift=quant_shift,
                        transform_mode=quant_transform,
                        target_mode=quant_target_mode,
                        direction_threshold=quant_direction_threshold,
                    )
                    if len(X) and len(y):
                        family = (
                            "classification" if quant_target_mode in {"binary_direction", "ternary_direction"}
                            else "volatility" if quant_target_mode == "future_volatility"
                            else "regression"
                        )
                        quant_data = run_quant_models(
                            X,
                            y,
                            QuantConfig(
                                target_mode=quant_target_mode,
                                horizon=quant_shift,
                                direction_threshold=quant_direction_threshold,
                                model_families={family: quant_models or [quant_model]},
                            ),
                            predict_rows=quant_predict_rows,
                        )
                except Exception as exc:
                    print(f"[Quant] backtest context unavailable: {exc}")

            web_data = None
            if web_search_enabled:
                print(f"[debug] step {completed}: collecting web context", flush=True)
                try:
                    web_data = search_web_context(
                        symbol,
                        aspects=web_search_aspects or [],
                        extra_terms=(web_search_extra_terms or []) + (web_search_topics or []),
                        max_results=web_search_max_results,
                        as_of=pd.to_datetime(df_all.iloc[i]['time']).to_pydatetime(),
                        require_published_at=True,
                    )
                except Exception as exc:
                    print(f"[Web] backtest context unavailable: {exc}")

            # Build LLM input
            market_info = build_llm_market_input(
                symbol, interval, current_df, snapshot,
                n=n, indicators=indicators_data, higher_tf=higher_tf_data,
                quant_data=quant_data,
                web_data=web_data,
            )

            # Run several inferences and require the same scenario from all of them,
            # matching the consistency check used by the live analysis workflow.
            responses = []
            try:
                for attempt in range(1, iterations + 1):
                    print(f"[debug] step {completed}: LLM inference {attempt}/{iterations}", flush=True)
                    selected_model = model_names[(attempt - 1) % len(model_names)]
                    prompt_text = None
                    if prompt_texts is not None:
                        prompt_text = select_prompt_text(prompt_texts, (attempt - 1) % len(model_names))
                    response, usage = inference(
                        market_info,
                        symbol,
                        interval,
                        web_context=web_data.get("context", "") if web_data else None,
                        model_name=selected_model,
                        prompt_text=prompt_text,
                    )
                    if selected_model:
                        response["model_name"] = selected_model
                    usage_input, usage_output, usage_total = parse_usage(usage)
                    total_input_tokens += usage_input
                    total_output_tokens += usage_output
                    total_tokens += usage_total
                    responses.append(response)
                    print(f"[debug] step {completed}: inference {attempt} scenario={response.get('scenario')} | tokens={usage_total}", flush=True)
            except Exception as e:
                print(f"Error in inference: {e}")
                continue

            scenarios = [str(response.get('scenario', '')).lower().strip() for response in responses]
            res, vote_status = winning_llm_response(responses)
            if vote_status == "no_trade":
                no_trade_windows += 1
                llm_windows.append({"status": "no_trade", "responses": responses})
                print(f"[consensus] {symbol} status=no_trade scenarios={scenarios}", flush=True)
                print(f"[debug] step {completed}: skipped; no_trade scenario returned", flush=True)
                continue
            if vote_status != "agree" or res is None:
                disagreement_windows += 1
                llm_windows.append({"status": "disagree", "responses": responses})
                print(f"[consensus] {symbol} status=disagree scenarios={scenarios}", flush=True)
                print(f"[debug] step {completed}: skipped; vote tied or mismatched scenarios={scenarios}", flush=True)
                continue
            agreement_windows += 1
            llm_window = {"status": "agree", "responses": responses}
            print(f"[consensus] {symbol} status=agree scenario={res.get('scenario')} votes={dict(Counter(scenarios))}", flush=True)
            print(f"[debug] step {completed}: vote confirmed ({res.get('scenario')}) after {iterations} inference(s)", flush=True)

            # Evaluate outcome
            future_candles = min(res['expected_time'], len(future_df))
            df_future_slice = future_df.iloc[:future_candles]
            outcome, return_pct = evaluate_trade_outcome(
                df_future_slice, res['scenario'], res['entry_price'],
                res['target_price'], res['stop_loss']
            )
            llm_window.update({
                "outcome": outcome,
                "confidence": res.get("confidence"),
            })
            llm_windows.append(llm_window)
            print(f"[debug] step {completed}: evaluated outcome={outcome}, return={return_pct:.2f}%", flush=True)

            # Update counters
            if outcome == 'success':
                wins += 1
                total_return += return_pct
            elif outcome == 'failure':
                losses += 1
                total_return += return_pct
            elif outcome == 'timeout':
                timeouts += 1

            # Record result
            chart_df = df_all.iloc[max(0, i - n + 1):i + 1 + max_expected_time]
            chart_candles = [
                {
                    "time": row["time"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
                for _, row in chart_df.iterrows()
            ]
            outcome_price = res["target_price"] if outcome == "success" else res["stop_loss"] if outcome == "failure" else res["entry_price"]
            outcome_time = df_future_slice.iloc[-1]["time"] if len(df_future_slice) else df_all.iloc[i]["time"]
            result = {
                'timestamp': df_all.iloc[i]['time'],
                'symbol': symbol,
                'scenario': res['scenario'],
                'confidence': res['confidence'],
                'entry_price': res['entry_price'],
                'target_price': res['target_price'],
                'stop_loss': res['stop_loss'],
                'expected_time': res['expected_time'],
                'outcome': outcome,
                'return_pct': return_pct,
                'analysis': res['analysis'],
                'entry_to_target': (res['target_price'] - res['entry_price']) / res['entry_price'] * 100 if res.get('entry_price') else 0.0,
                'entry_to_stop': (res['stop_loss'] - res['entry_price']) / res['entry_price'] * 100 if res.get('entry_price') else 0.0,
                'chart_candles': chart_candles,
                'chart_marker': {
                    'entry_time': df_all.iloc[i]['time'],
                    'entry_price': res['entry_price'],
                    'outcome': outcome,
                    'outcome_time': outcome_time,
                    'outcome_price': outcome_price,
                },
                'web_context': web_data or {"results": [], "context": ""},
            }
            symbol_results.append(result)
            # persist per-symbol results incrementally so the dashboard can display completed trades in real time
            try:
                out_dir = os.path.join(os.getcwd(), "backtest_results")
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, f"{symbol}_results.json"), 'w', encoding='utf-8') as fh:
                    json.dump(symbol_results, fh, indent=2, default=str)
            except Exception as exc:
                print(f"[backtest] could not write incremental results file: {exc}")
            # append to ML dataset for later training/labeling
            try:
                ml_record = {
                    'mode': 'backtest',
                    'symbol': symbol,
                    'timestamp': result['timestamp'],
                    'predicted_label': result['scenario'],
                    'confidence': result.get('confidence'),
                    'entry_price': result.get('entry_price'),
                    'target_price': result.get('target_price'),
                    'stop_loss': result.get('stop_loss'),
                    'expected_time': result.get('expected_time'),
                    'analysis': result.get('analysis'),
                    'model_name': result.get('model_name'),
                    'outcome': result.get('outcome'),
                    'return_pct': result.get('return_pct'),
                    'chart_marker': result.get('chart_marker'),
                    'web_context': result.get('web_context'),
                    'quant_data': quant_data,
                    # include the full LLM input used for prediction so downstream training
                    # has all features (price history, indicators, quant output, web context)
                    'features': (json.loads(market_info) if isinstance(market_info, str) else market_info),
                }
                append_record(ml_record)
            except Exception as exc:
                print(f"[ml_data] could not append record: {exc}")

            current_cost = total_input_tokens * input_token_price + total_output_tokens * output_token_price
            print(
                f"Time: {result['timestamp']} | Scenario: {result['scenario']} | Confidence: {result['confidence']:.2f} | "
                f"Outcome: {outcome} | Return: {return_pct:.2f}% | "
                f"Input tokens: {total_input_tokens} | Output tokens: {total_output_tokens} | "
                f"Cost: ${current_cost:.4f}"
            )

            # Check if token or dollar limit exceeded
            if total_tokens > token_limit:
                print(f"Token limit ({token_limit}) exceeded, stopping backtest.")
                break
            if max_cost and current_cost > max_cost:
                print(f"Cost limit (${max_cost:.2f}) exceeded (current ${current_cost:.2f}), stopping backtest.")
                break

        business_metrics = compute_business_metrics(symbol_results)
        llm_performance = compute_llm_performance_metrics(llm_windows, iterations)
        results[symbol] = {
            'results': symbol_results,
            'total_trades': len(symbol_results),
            'wins': wins,
            'losses': losses,
            'timeouts': timeouts,
            'success_rate': wins / len(symbol_results) if symbol_results else 0,
            'total_return': total_return,
            'avg_return_per_trade': total_return / len(symbol_results) if symbol_results else 0,
            'buy_and_hold_return': buy_and_hold_return,
            'outperformance': total_return - buy_and_hold_return,
            'business_metrics': business_metrics,
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'total_tokens': total_tokens,
            'total_cost': total_input_tokens * input_token_price + total_output_tokens * output_token_price,
            'actual_start': actual_start,
            'actual_end': actual_end,
            'requested_lookback': lookback,
            'inferences_per_trade': iterations,
            'llm_models': model_names,
            'llm_consensus': {
                'agreed_windows': agreement_windows,
                'disagreed_windows': disagreement_windows,
                'no_trade_windows': no_trade_windows,
                'agreement_ratio': llm_performance['agreement_ratio'],
            },
            'llm_performance': llm_performance,
        }

        print(f"\n{symbol} Summary:")
        print(f"Requested candles: {lookback}")
        print(f"Actual window: {actual_start} to {actual_end}")
        print(f"Total Trades: {results[symbol]['total_trades']}")
        print(f"Wins: {wins}, Losses: {losses}, Timeouts: {timeouts}")
        print(f"Success Rate: {results[symbol]['success_rate']:.2%}")
        print(f"Total Return: {total_return:.2f}%")
        print(f"Avg Return per Trade: {results[symbol]['avg_return_per_trade']:.2f}%")
        print(f"Buy & Hold Return: {buy_and_hold_return:.2f}%")
        print(f"Outperformance: {results[symbol]['outperformance']:.2f}%")
        print(f"Win Rate: {results[symbol]['business_metrics']['win_rate']:.2%}")
        print(f"Profit Factor: {results[symbol]['business_metrics']['profit_factor']:.2f}")
        print(f"Avg Win: {results[symbol]['business_metrics']['avg_win']:.2f}%")
        print(f"Avg Loss: {results[symbol]['business_metrics']['avg_loss']:.2f}%")
        print(f"Avg Trade Duration: {results[symbol]['business_metrics']['average_trade_duration']:.2f} candles")
        print(f"Max Drawdown: {results[symbol]['business_metrics']['max_drawdown']:.2f}%")
        print(f"Input Tokens: {total_input_tokens}, Output Tokens: {total_output_tokens}, Total Tokens: {total_tokens}")
        print(f"Total Cost: ${results[symbol]['total_cost']:.4f}")
        consensus = results[symbol]['llm_consensus']
        print(f"LLM Consensus: {consensus['agreed_windows']} agreed, {consensus['disagreed_windows']} disagreed, {consensus['no_trade_windows']} no-trade | Agreement ratio: {consensus['agreement_ratio']:.2%}")
        performance = results[symbol]['llm_performance']
        print(f"LLM Direction Accuracy: {performance['direction_accuracy']:.2%}")
        print(f"LLM Confidence Calibration Error: {performance['confidence_calibration_error']:.2%}")
        print(f"LLM Decision Stability: {performance['decision_stability']:.2%}")
        if max_cost > 0:
            print(f"Max Cost Cap: ${max_cost:.2f}")

    results['total_tokens'] = total_tokens
    return results


# Function: save_results
def save_results(results: Dict[str, Any], output_dir: str = "backtest_results"):
    """
    Save backtest results to files.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Save summary
    summary = {
        'total_tokens': results['total_tokens'],
        'symbols': {}
    }

    for symbol, data in results.items():
        if symbol == 'total_tokens':
            continue
        summary['symbols'][symbol] = {
            'total_trades': data['total_trades'],
            'wins': data['wins'],
            'losses': data['losses'],
            'timeouts': data['timeouts'],
            'success_rate': data['success_rate'],
            'total_return': data['total_return'],
            'avg_return_per_trade': data['avg_return_per_trade'],
            'buy_and_hold_return': data['buy_and_hold_return'],
            'outperformance': data['outperformance'],
            'business_metrics': data['business_metrics'],
            'input_tokens': data['input_tokens'],
            'output_tokens': data['output_tokens'],
            'total_tokens': data['total_tokens'],
            'total_cost': data['total_cost'],
            'requested_lookback': data['requested_lookback'],
            'actual_start': data['actual_start'],
            'actual_end': data['actual_end'],
            'inferences_per_trade': data['inferences_per_trade'],
            'llm_models': data.get('llm_models', []),
            'llm_consensus': data['llm_consensus'],
            'llm_performance': data['llm_performance'],
        }

        # Save detailed results
        df_results = pd.DataFrame(data['results'])
        df_results.to_csv(os.path.join(output_dir, f"{symbol}_results.csv"), index=False)
        with open(os.path.join(output_dir, f"{symbol}_results.json"), 'w') as f:
            json.dump(data['results'], f, indent=2, default=str)

    with open(os.path.join(output_dir, "summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults saved to {output_dir}")


# Function: parse_arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description="Backtesting for Trading View Analysis System")
    parser.add_argument(
        '-s', '--symbols',
        nargs='+',
        default=DEFAULT_SYMBOLS[:2],  # Default to first 2 for testing
        help=f'Symbols to backtest (default: {DEFAULT_SYMBOLS[:2]})'
    )
    parser.add_argument(
        '--lookback',
        type=int,
        default=DEFAULT_LIMIT,
        help=f'Number of most recent candles to load (default: {DEFAULT_LIMIT})'
    )
    parser.add_argument(
        '--interval',
        default=DEFAULT_INTERVAL,
        help=f'Timeframe interval (default: {DEFAULT_INTERVAL})'
    )
    parser.add_argument(
        '--step',
        type=int,
        default=10,
        help='Step size in candles between tests (default: 10)'
    )
    parser.add_argument(
        '--iterations',
        type=int,
        default=2,
        help='Number of inferences per trade window; all scenarios must agree (default: 2)'
    )
    parser.add_argument(
        '--model-names',
        nargs='+',
        default=None,
        help=f'One or more OpenRouter model names used across iterations for voting (default: {MODEL_NAME} from .env)'
    )
    parser.add_argument(
        '--prompt-files',
        nargs='+',
        default=None,
        help='One or more prompt file paths. If one file is provided, all models use it. If multiple files are provided, each model uses the corresponding prompt file.'
    )
    parser.add_argument(
        '--n',
        type=int,
        default=DEFAULT_N,
        help=f'Number of recent candles for LLM input (default: {DEFAULT_N})'
    )
    parser.add_argument(
        '--higher-timeframes',
        nargs='+',
        default=DEFAULT_HIGHER_TIMEFRAMES,
        help=f'Higher timeframe intervals (default: {DEFAULT_HIGHER_TIMEFRAMES})'
    )
    parser.add_argument(
        '--indicators',
        nargs='+',
        default=DEFAULT_INDICATORS,
        help=f'Indicator columns to include (default: {DEFAULT_INDICATORS})'
    )
    parser.add_argument(
        '--max-expected-time',
        type=int,
        default=12,
        help='Maximum expected time in candles (default: 12)'
    )
    parser.add_argument(
        '--token-limit',
        type=int,
        default=1500000,
        help='Maximum token usage limit (default: 1500000)'
    )
    parser.add_argument(
        '--input-token-price',
        type=float,
        default=0.0,
        help='Price per input token for cost calculation (default: 0.0)'
    )
    parser.add_argument(
        '--output-token-price',
        type=float,
        default=0.0,
        help='Price per output token for cost calculation (default: 0.0)'
    )
    parser.add_argument(
        '--max-cost',
        type=float,
        default=1.0,
        help='Maximum dollar cost for token usage (default: 1.0)'
    )
    parser.add_argument(
        '--output-dir',
        default='backtest_results',
        help='Output directory for results (default: backtest_results)'
    )
    parser.add_argument(
        '--quant-enabled',
        action='store_true',
        help='Enable quant context during backtesting'
    )
    parser.add_argument(
        '--quant-input-data',
        choices=['ohlcv', 'indicators', 'both'],
        default='both',
        help='Quant input data source during backtesting (default: both)'
    )
    parser.add_argument(
        '--quant-model',
        choices=sorted(set(available_models()) | set(available_classifiers())),
        default='random_forest',
        help='Quant model to use during backtesting (default: random_forest)'
    )
    parser.add_argument('--quant-models', nargs='+', default=None)
    parser.add_argument('--quant-target-mode', choices=available_target_modes(), default='raw_price')
    parser.add_argument('--quant-direction-threshold', type=float, default=0.001)
    parser.add_argument(
        '--quant-transform',
        default='none',
        help='Quant transformation mode during backtesting (default: none)'
    )
    parser.add_argument(
        '--quant-output-target',
        default='close',
        help='Quant target column during backtesting (default: close)'
    )
    parser.add_argument(
        '--quant-shift',
        type=int,
        default=1,
        help='Quant shift value during backtesting (default: 1)'
    )
    parser.add_argument(
        '--quant-predict-rows',
        type=int,
        default=1,
        help='Number of rows used for quant predictions (default: 1)'
    )
    parser.add_argument(
        '--web-search-enabled',
        action='store_true',
        help='Enable web-search context during backtesting'
    )
    parser.add_argument(
        '--web-search-aspects',
        nargs='+',
        default=['policy', 'news', 'macro', 'exchange'],
        help='Web-search aspects used during backtesting'
    )
    parser.add_argument(
        '--web-search-extra-terms',
        nargs='+',
        default=[],
        help='Extra terms appended to the web-search query'
    )
    parser.add_argument(
        '--web-search-topics',
        nargs='+',
        default=[],
        help='Web-search topics used during backtesting'
    )
    parser.add_argument(
        '--web-search-max-results',
        type=int,
        default=5,
        help='Maximum number of web results included during backtesting'
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
    if args.prompt_files and len(args.prompt_files) not in (1, len(args.model_names)):
        parser.error("--prompt-files must either be a single shared prompt or match the number of --model-names")
    if args.iterations < 1:
        parser.error("--iterations must be greater than or equal to 1")
    if args.lookback < 1:
        parser.error("--lookback must be greater than or equal to 1")
    if args.step < 1:
        parser.error("--step must be greater than or equal to 1")
    if args.step >= args.lookback:
        parser.error("--step must be smaller than --lookback")
    if args.n < 1:
        parser.error("--n must be greater than or equal to 1")
    if args.max_expected_time < 1:
        parser.error("--max-expected-time must be greater than or equal to 1")
    if args.lookback <= args.n + args.max_expected_time:
        parser.error("--lookback must be greater than --n + --max-expected-time")
    if args.token_limit < 1:
        parser.error("--token-limit must be greater than or equal to 1")
    if args.input_token_price < 0:
        parser.error("--input-token-price must be greater than or equal to 0")
    if args.output_token_price < 0:
        parser.error("--output-token-price must be greater than or equal to 0")
    if args.max_cost < 0:
        parser.error("--max-cost must be greater than or equal to 0")
    if not str(args.output_dir or "").strip():
        parser.error("--output-dir must not be empty")
    if args.quant_shift < 1:
        parser.error("--quant-shift must be greater than or equal to 1")
    if args.quant_predict_rows < 1:
        parser.error("--quant-predict-rows must be greater than or equal to 1")
    if args.quant_direction_threshold < 0:
        parser.error("--quant-direction-threshold must be greater than or equal to 0")
    if args.web_search_max_results < 1:
        parser.error("--web-search-max-results must be greater than or equal to 1")


if __name__ == "__main__":
    args = parse_arguments()
    print("🚀 Starting Backtesting")
    print(f"📊 Symbols: {args.symbols}")
    print(f"📅 Lookback: {args.lookback} candles")
    print(f"⏰ Interval: {args.interval}")
    print(f"📈 Step: {args.step}")
    print(f"💰 Token prices: input ${args.input_token_price:.6f}, output ${args.output_token_price:.6f}")
    print("=" * 50)

    results = run_backtest(
        symbols=args.symbols,
        lookback=args.lookback,
        interval=args.interval,
        step=args.step,
        iterations=args.iterations,
        model_names=args.model_names,
        n=args.n,
        higher_timeframes=args.higher_timeframes,
        indicators=args.indicators,
        max_expected_time=args.max_expected_time,
        token_limit=args.token_limit,
        input_token_price=args.input_token_price,
        output_token_price=args.output_token_price,
        max_cost=args.max_cost,
        quant_enabled=args.quant_enabled,
        quant_input_data=args.quant_input_data,
        quant_model=args.quant_model,
        quant_models=args.quant_models,
        quant_target_mode=args.quant_target_mode,
        quant_direction_threshold=args.quant_direction_threshold,
        quant_transform=args.quant_transform,
        quant_output_target=args.quant_output_target,
        quant_shift=args.quant_shift,
        quant_predict_rows=args.quant_predict_rows,
        web_search_enabled=args.web_search_enabled,
        web_search_aspects=args.web_search_aspects,
        web_search_extra_terms=args.web_search_extra_terms,
        web_search_topics=args.web_search_topics,
        web_search_max_results=args.web_search_max_results,
        prompt_files=args.prompt_files,
    )
    save_results(results, args.output_dir)
