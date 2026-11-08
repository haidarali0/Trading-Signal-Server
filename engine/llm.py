import json
from collections.abc import Mapping
import numpy as np
from pathlib import Path
import requests
from openai import APIConnectionError, APIStatusError, OpenAI
import json_repair
from engine.llm_prompt import prompt as default_prompt
from config import (
    DECISION_MODELS,
    OPENROUTER_API_KEY as API,
    TYPESAFE_API_KEY,
    MODEL_NAME,
)


DECISION_API_URL = "https://openrouter.ai/api/alpha/decisions"


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
        }
        data["volatility"] = snapshot["volatility"]
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


def format_inference_prompt(
    info,
    symbol,
    time_frame,
    web_context=None,
    prompt_text=None,
    skill_instructions=None,
):
    """Format the base/custom prompt and append optional additive skill guidance."""
    template = prompt_text if prompt_text is not None else default_prompt
    formatted_prompt = template.format(
        symbol=symbol,
        time_frame=time_frame,
        info=info,
        web_context=web_context or "No external context available.",
    )
    instructions = str(skill_instructions or "").strip()
    if instructions:
        formatted_prompt += (
            "\n\nSupplemental skill instructions (do not replace or contradict "
            "the required output format above):\n"
            f"{instructions}"
        )
    return formatted_prompt


def _decision_trade_prices(market_data, scenario, current_price, target_price=None):
    """Derive application-required trade levels from Fibonacci features or ATR."""
    if scenario == "no_trade":
        return current_price, current_price

    fib = (market_data.get("derived_features") or {}).get("fibonacci") or {}
    levels_data = fib.get("retracement_levels") if fib.get("status") == "ok" else {}
    levels = []
    if isinstance(levels_data, dict):
        for raw_level in levels_data.values():
            try:
                level = float(raw_level)
            except (TypeError, ValueError):
                continue
            if np.isfinite(level) and level > 0:
                levels.append(level)

    history = market_data.get("price_history") or []
    atr = None
    if history and isinstance(history[0], dict):
        try:
            atr = float(history[0].get("atr"))
        except (TypeError, ValueError):
            pass
    if atr is None or not np.isfinite(atr) or atr <= 0:
        atr = current_price * 0.01

    below = [level for level in levels if level < current_price]
    above = [level for level in levels if level > current_price]
    if scenario == "up":
        target = target_price if target_price is not None else min(above) if above else current_price + atr
        stop = max(below) if below else current_price - atr
    else:
        target = target_price if target_price is not None else max(below) if below else current_price - atr
        stop = min(above) if above else current_price + atr
    return target, stop


def _post_decision_request(model_name, request_payload):
    """Send and validate one OpenRouter decisions request."""
    try:
        response = requests.post(
            DECISION_API_URL,
            headers={
                "Authorization": f"Bearer {API}",
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=120,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        detail = exc.response.text if exc.response is not None else str(exc)
        if status_code == 401:
            guidance = "Check that OPENROUTER_API_KEY is valid and active."
        elif status_code == 403:
            guidance = "Check API key permissions and whether this model is available to your account."
        elif status_code == 402:
            guidance = "Check your OpenRouter account credits and billing."
        elif status_code == 404:
            guidance = f"Check that the decision model '{model_name}' is available."
        else:
            guidance = "Check your API key, model configuration, and OpenRouter service status."
        raise RuntimeError(
            f"[OpenRouter] Decision API request failed (HTTP {status_code}). "
            f"{guidance} Details: {detail}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(
            f"[OpenRouter] Could not complete decision API request: {exc}"
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("[OpenRouter] Decision API returned invalid JSON.") from exc
    if not isinstance(body, dict):
        raise RuntimeError("[OpenRouter] Decision API response must be a JSON object.")
    return body


def _typesafe_decision_answers(state, questions, level_criteria, model_name):
    """Call Jev directly through the TypeSafe SDK and normalize its typed answers."""
    if not TYPESAFE_API_KEY:
        raise RuntimeError(
            "[TypeSafe] TYPESAFE_API_KEY is required for direct Jev API access."
        )
    try:
        from typesafe_sdk import Choice, Noul, TypeSafeClient
    except ImportError as exc:
        raise RuntimeError(
            "[TypeSafe] Direct Jev API access requires typesafe-sdk. "
            "Install the project requirements."
        ) from exc

    sdk_questions = {
        "target_level": Choice(
            instructions=questions["target_level"]["instructions"],
            criteria=level_criteria,
        )
    }
    if "trade_success" in questions:
        sdk_questions["trade_success"] = Noul(
            instructions=questions["trade_success"]["instructions"],
            criteria=questions["trade_success"]["criteria"],
        )

    typesafe_model = {
        "typesafe/jev-1.13": "jev-1.13.0",
        "typesafe/jev-1.14": "jev-1.14.0",
    }.get(model_name.casefold(), model_name.partition("/")[2] or model_name)
    with TypeSafeClient(api_key=TYPESAFE_API_KEY, model=typesafe_model) as client:
        response = client.system_one(state=state, questions=sdk_questions)

    grouped_answers = getattr(response, "answers", None)
    if isinstance(grouped_answers, Mapping) and "target_level" in grouped_answers:
        target_answer = grouped_answers["target_level"]
    else:
        choices = getattr(response, "choices", None)
        target_answer = choices.get("target_level") if isinstance(choices, Mapping) else None
    if target_answer is None:
        raise RuntimeError("[TypeSafe] Response is missing the target_level choice.")

    probabilities = getattr(target_answer, "probabilities", None)
    if not isinstance(probabilities, Mapping):
        raise RuntimeError("[TypeSafe] Response is missing target-level probabilities.")
    normalized_answers = {
        "target_level": {
            "choice": getattr(target_answer, "choice", None),
            "confidence": getattr(target_answer, "confidence", None),
            "probabilities": probabilities,
        }
    }
    if "trade_success" in questions:
        if isinstance(grouped_answers, Mapping) and "trade_success" in grouped_answers:
            success_answer = grouped_answers["trade_success"]
        else:
            nouls = getattr(response, "nouls", None)
            success_answer = nouls.get("trade_success") if isinstance(nouls, Mapping) else None
        if success_answer is None:
            raise RuntimeError("[TypeSafe] Response is missing the trade_success noul.")
        normalized_answers["trade_success"] = {
            "noul": getattr(success_answer, "noul", None),
        }

    return {
        "answers": normalized_answers,
        "usage": getattr(response, "usage", None),
    }


def _decision_inference(
    formatted_prompt,
    model_name,
    market_info,
    scoring_horizon=None,
):
    """Call Jev through the selected provider and adapt its choice to a signal."""
    try:
        market_data = json.loads(market_info)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Decision model requires market_info to be valid JSON.") from exc
    if not isinstance(market_data, dict):
        raise ValueError("Decision model requires market_info to be a JSON object.")
    forecast_horizon = max(1, int(scoring_horizon or 12))

    market = market_data.get("market") or {}
    current_price = market.get("current_price")
    if current_price is None:
        history = market_data.get("price_history") or []
        current_price = history[0].get("close") if history and isinstance(history[0], dict) else None
    try:
        current_price = float(current_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Decision model requires a numeric current market price.") from exc
    if not np.isfinite(current_price) or current_price <= 0:
        raise ValueError("Decision model requires a finite positive current market price.")

    fib = (market_data.get("derived_features") or {}).get("fibonacci") or {}
    raw_levels = fib.get("retracement_levels") if fib.get("status") == "ok" else {}
    candidates = []
    if isinstance(raw_levels, dict):
        parsed_levels = []
        for ratio, raw_price in raw_levels.items():
            try:
                ratio_value = float(ratio)
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            if np.isfinite(ratio_value) and np.isfinite(price) and price > 0:
                parsed_levels.append((ratio_value, str(ratio), price))
        for index, (ratio_value, ratio, price) in enumerate(sorted(parsed_levels), start=1):
            choice_id = f"level_{index}"
            if price > current_price:
                position = "above current price"
            elif price < current_price:
                position = "below current price"
            else:
                position = "at current price"
            candidates.append({
                "choice": choice_id,
                "ratio": ratio,
                "price": price,
                "ratio_value": ratio_value,
                "position": position,
            })

    level_criteria = {
        candidate["choice"]: (
            f"Fibonacci {candidate['ratio']} retracement at price "
            f"{candidate['price']:.12g}, {candidate['position']}."
        )
        for candidate in candidates
    }
    if not level_criteria:
        level_criteria["no_trade"] = (
            "No usable Fibonacci levels are available; do not invent a target."
        )
    else:
        level_criteria["no_trade"] = (
            "No Fibonacci target level is sufficiently likely or the evidence is unclear."
        )

    request_state = formatted_prompt
    questions = {
        "target_level": {
            "type": "choice",
            "instructions": (
                "Choose the single Fibonacci level most likely to be the next meaningful "
                "price touch or support/resistance reaction. Consider every listed level, "
                "its position relative to current price, recent price action, and direction. "
                "Do not choose a level merely because it is closest; choose no_trade if "
                "the evidence does not support a likely next level."
            ),
            "criteria": level_criteria,
        }
    }
    if scoring_horizon is not None:
        trade_scenarios = []
        for candidate in candidates:
            target_price = candidate["price"]
            if target_price > current_price:
                scenario = "up"
            elif target_price < current_price:
                scenario = "down"
            else:
                scenario = "no_trade"
            _, stop_price = _decision_trade_prices(
                market_data,
                scenario,
                current_price,
                target_price=target_price,
            )
            trade_scenarios.append(
                f"{candidate['choice']}: scenario={scenario}, target={target_price:.12g}, "
                f"stop-loss={stop_price:.12g}"
            )
        request_state += (
            "\n\nBacktest trade-success evaluation:\n"
            f"Evaluate the target selected by the target_level question using the matching "
            f"scenario below. Entry price: {current_price:.12g}. "
            f"Evaluation horizon: {forecast_horizon} candles.\n"
            + "\n".join(trade_scenarios)
        )
        request_state += (
            "\nno_trade: no position is opened; this is not a successful trade."
        )
        questions["trade_success"] = {
            "type": "noul",
            "instructions": (
                "For the target selected by target_level, estimate the probability that "
                "price reaches its listed target before its listed stop-loss within "
                f"{forecast_horizon} candles. A stop-loss reached first or neither barrier "
                "reached within the horizon means the event is false. Use the trade scenario "
                "and levels in the request state; do not use the target_level choice "
                "probability as this probability."
            ),
            "criteria": {
                "true": (
                    "The target selected by target_level is reached before its corresponding "
                    f"stop-loss within {forecast_horizon} candles."
                ),
                "false": (
                    "The corresponding stop-loss is reached first, or the selected target "
                    f"is not reached within {forecast_horizon} candles."
                ),
            },
        }

    request_payload = {
        "model": model_name,
        "state": request_state,
        "questions": questions,
    }
    jev_provider = "typesafe" if TYPESAFE_API_KEY else "openrouter"
    if jev_provider == "typesafe":
        body = _typesafe_decision_answers(
            request_state,
            questions,
            level_criteria,
            model_name,
        )
    else:
        body = _post_decision_request(model_name, request_payload)
    provider_label = "TypeSafe" if jev_provider == "typesafe" else "OpenRouter"
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise RuntimeError(f"[{provider_label}] Decision API response is missing answers.")
    answer = answers.get("target_level")
    if not isinstance(answer, dict):
        raise RuntimeError(
            f"[{provider_label}] Decision API response is missing answers.target_level."
        )
    picked = str(answer.get("choice", ""))
    candidate_by_choice = {candidate["choice"]: candidate for candidate in candidates}
    if picked != "no_trade" and picked not in candidate_by_choice:
        raise RuntimeError(
            f"[{provider_label}] Decision API returned unknown target level '{picked}'."
        )
    raw_probabilities = answer.get("probabilities")
    if not isinstance(raw_probabilities, dict):
        raise RuntimeError(
            f"[{provider_label}] Decision API response is missing target-level probabilities."
        )

    probabilities = {}
    for choice_id, raw_probability in raw_probabilities.items():
        choice_id = str(choice_id)
        if choice_id != "no_trade" and choice_id not in candidate_by_choice:
            raise RuntimeError(
                f"[{provider_label}] Decision API returned probability for unknown target '{choice_id}'."
            )
        try:
            probability = float(raw_probability)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"[{provider_label}] Decision API returned an invalid probability for '{choice_id}'."
            ) from exc
        if not np.isfinite(probability) or not 0 <= probability <= 1:
            raise RuntimeError(
                f"[{provider_label}] Decision API returned an out-of-range probability for '{choice_id}'."
            )
        probabilities[choice_id] = probability
    if picked not in probabilities:
        raise RuntimeError(
            f"[{provider_label}] Decision API probabilities do not include the picked target."
        )

    target_candidate = candidate_by_choice.get(picked)
    if target_candidate is None:
        scenario = "no_trade"
        target_ratio = None
        selected_target = None
    else:
        selected_target = target_candidate["price"]
        target_ratio = target_candidate["ratio"]
        if selected_target > current_price:
            scenario = "up"
        elif selected_target < current_price:
            scenario = "down"
        else:
            scenario = "no_trade"
    confidence = probabilities[picked]
    target, stop = _decision_trade_prices(
        market_data,
        scenario,
        current_price,
        target_price=selected_target,
    )
    trade_success_probability = None
    if scoring_horizon is not None:
        success_answer = answers.get("trade_success")
        if not isinstance(success_answer, dict):
            raise RuntimeError(
                f"[{provider_label}] Decision API response is missing answers.trade_success."
            )
        if "noul" not in success_answer:
            raise RuntimeError(
                f"[{provider_label}] Decision API response is missing "
                "answers.trade_success.noul."
            )
        try:
            trade_success_probability = float(success_answer["noul"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"[{provider_label}] Decision API returned an invalid trade-success probability."
            ) from exc
        if (
            not np.isfinite(trade_success_probability)
            or not 0 <= trade_success_probability <= 1
        ):
            raise RuntimeError(
                f"[{provider_label}] Decision API returned an out-of-range trade-success probability."
            )

    named_probabilities = {
        candidate_by_choice[choice_id]["ratio"] if choice_id != "no_trade" else "no_trade": probability
        for choice_id, probability in probabilities.items()
    }
    print(f"Picked Fibonacci target: {target_ratio or 'no_trade'} ({target:g})")
    print(f"Target probabilities: {named_probabilities}")
    if confidence > 0.6:
        print(f"Confident target: {target_ratio or 'no_trade'}")
    else:
        print(
            f"Low-confidence target: {target_ratio or 'no_trade'} "
            "(consider asking again or prompting more)"
        )

    return {
        "scenario": scenario,
        "confidence": confidence,
        "entry_price": current_price,
        "target_price": target,
        "stop_loss": stop,
        "expected_time": forecast_horizon,
        "analysis": "",
        "target_fibonacci_level": target_ratio,
        "target_fibonacci_price": selected_target,
        "decision_probabilities": named_probabilities,
        "trade_success_probability": trade_success_probability,
        "model_name": model_name,
    }, body.get("usage")


def inference(
    info,
    symbol,
    time_frame,
    web_context=None,
    model_name=None,
    prompt_text=None,
    skill_instructions=None,
    scoring_horizon=None,
):
    selected_model = model_name or MODEL_NAME
    print(f"[LLM] stage: sending request for {symbol} @ {time_frame} with {selected_model}...")
    formatted_prompt = format_inference_prompt(
        info,
        symbol=symbol,
        time_frame=time_frame,
        web_context=web_context or "No external context available.",
        prompt_text=prompt_text,
        skill_instructions=skill_instructions,
    )
    if selected_model.strip().casefold() in {
        name.casefold() for name in DECISION_MODELS
    }:
        return _decision_inference(
            formatted_prompt,
            selected_model,
            info,
            scoring_horizon=scoring_horizon,
        )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API,
    )
    if scoring_horizon is not None:
        formatted_prompt += (
            "\n\nBacktest confidence semantics: confidence is the probability (0 to 1) "
            f"that this response's proposed target is reached before its stop-loss within "
            f"{int(scoring_horizon)} candles. If neither barrier is reached in that common "
            "backtest horizon, the outcome is not a success."
        )
    elif prompt_text is not None:
        formatted_prompt += (
            "\n\nConfidence semantics: set confidence to the probability (0 to 1) "
            "that this response's proposed target is reached before its stop-loss "
            "within expected_time. If neither barrier is reached, the outcome is "
            "not a success. Do not use confidence to mean general certainty."
        )

    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {
                    "role": "user",
                    "content": formatted_prompt
                }
            ],
            max_tokens=8192,
            extra_body={"reasoning": {"enabled": True}}
        )
    except APIConnectionError as exc:
        raise RuntimeError(
            "[OpenRouter] Could not connect to the API. Check your internet connection "
            "and OpenRouter service status."
        ) from exc
    except APIStatusError as exc:
        if exc.status_code == 401:
            guidance = "Check that OPENROUTER_API_KEY is valid and active."
        elif exc.status_code == 403:
            guidance = "Check API key permissions and whether this model is available to your account."
        elif exc.status_code == 402:
            guidance = "Check your OpenRouter account credits and billing."
        elif exc.status_code == 404:
            guidance = f"Check that the model name '{selected_model}' is available on OpenRouter."
        else:
            guidance = "Check your API key, model configuration, and OpenRouter service status."
        raise RuntimeError(
            f"[OpenRouter] API request failed (HTTP {exc.status_code}). {guidance} "
            f"Details: {exc}"
        ) from exc
    res = json_repair.loads(response.choices[0].message.content)
    if not isinstance(res, dict):
        raise RuntimeError(
            f"[OpenRouter] Model returned a {type(res).__name__}; "
            "expected a JSON object signal. Check that the selected prompt "
            "requests the required signal JSON format."
        )
    usage = response.usage
    print(f"[LLM] response received for {symbol} @ {time_frame}. Usage: {usage}")
    return res, usage
