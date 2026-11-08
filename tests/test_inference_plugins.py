import json
from types import SimpleNamespace

import pandas as pd
import pytest

from engine.llm import build_llm_market_input, format_inference_prompt, load_prompt_texts
from plugins.base import validate_inference_result
from plugins.dispatch import run_inference
from plugins import (
    apply_preprocessors,
    decision_model_setup_warning,
    format_extension_selection,
)
from skills import available_skills, load_skill_instructions


def test_default_chat_prompt_is_loaded_from_prompt_library():
    import engine.llm as llm

    prompt = load_prompt_texts(["prompts/genai_default_trading.txt"])[0]
    formatted_default = format_inference_prompt(
        '{"market": {"current_price": 100}}',
        "BTCUSDT",
        "1h",
    )
    formatted_explicit = format_inference_prompt(
        '{"market": {"current_price": 100}}',
        "BTCUSDT",
        "1h",
        prompt_text=prompt,
    )

    assert prompt == llm.default_prompt
    assert formatted_default == formatted_explicit
    assert "OUTPUT FORMAT (STRICT JSON)" in formatted_default
    assert '"scenario": "up" | "down" | "no_trade"' in formatted_default
    assert "{info}" not in formatted_default
    assert "{web_context}" not in formatted_default


def test_extension_selection_summary_formats_cli_and_dashboard_values():
    assert format_extension_selection(
        "custom.backend:SignalPlugin",
        "risk_first",
        ["fibonacci", "none"],
    ) == (
        "[extensions] Inference plugin: custom.backend:SignalPlugin | Inference skill: risk_first | "
        "Preprocessors: fibonacci, none | Prompt: default | "
        "Provider: not applicable (plugin-managed)"
    )
    assert format_extension_selection("model", "default", "none") == (
        "[extensions] Inference plugin: model | Inference skill: default | "
        "Preprocessors: none | Prompt: default | Provider: OpenRouter"
    )
    assert format_extension_selection(
        "model",
        "default",
        ["fibonacci"],
        prompt_files=["prompts/fibonacci_decision.txt"],
        model_names=["typesafe/jev-1.13"],
        direct_typesafe_available=True,
    ) == (
        "[extensions] Inference plugin: model | Inference skill: default | "
        "Preprocessors: fibonacci | Prompt: prompts/fibonacci_decision.txt | "
        "Provider: TypeSafe direct API"
    )
    assert "TypeSafe direct for Jev; OpenRouter for other models" in format_extension_selection(
        "model",
        "default",
        model_names=["typesafe/jev-1.13", "openai/gpt-4o-mini"],
        direct_typesafe_available=True,
    )


def test_jev_setup_warning_identifies_missing_features_and_prompt():
    assert decision_model_setup_warning(
        "model",
        ["typesafe/jev-1.13"],
        ["none"],
    ) == (
        "[setup] Jev's current target workflow expects Fibonacci levels; add "
        "--preprocessors fibonacci or a custom preprocessor supplying "
        "derived_features.fibonacci. The default chat prompt is not suitable "
        "for Jev; use --prompt-files prompts/fibonacci_decision.txt or a "
        "compatible custom Jev prompt."
    )
    assert decision_model_setup_warning(
        "model",
        ["typesafe/jev-1.13"],
        ["fibonacci"],
    ) is not None
    assert decision_model_setup_warning(
        "model",
        ["typesafe/jev-1.13"],
        ["fibonacci"],
        ["prompts/fibonacci_decision.txt"],
    ) is None
    assert decision_model_setup_warning(
        "custom.plugin:Inference",
        ["typesafe/jev-1.13"],
        ["none"],
    ) is None


def test_fibonacci_decision_prompt_is_chat_json_and_formats_state():
    prompt = load_prompt_texts(["prompts/fibonacci_decision.txt"])[0]
    formatted = format_inference_prompt(
        '{"derived_features": {"fibonacci": {"status": "ok"}}}',
        "BTCUSDT",
        "1h",
        prompt_text=prompt,
    )

    assert "Select the most plausible next" in formatted
    assert "Return only this JSON object" in formatted
    assert '"scenario": "up" | "down" | "no_trade"' in formatted
    assert "derived_features.fibonacci.retracement_levels" in formatted
    assert "Market state for BTCUSDT on 1h" in formatted
    assert "{info}" not in formatted
    assert "{symbol}" not in formatted


def test_fibonacci_jev_backup_prompt_is_typed_choice_and_formats_state():
    prompt = load_prompt_texts(["prompts/fibonacci_jev_backup_decision.txt"])[0]
    formatted = format_inference_prompt(
        '{"derived_features": {"fibonacci": {"status": "ok"}}}',
        "BTCUSDT",
        "1h",
        prompt_text=prompt,
    )

    assert "typed-choice interface" in formatted
    assert "Return only one exact typed choice" in formatted
    assert "Do not return" in formatted
    assert "{info}" not in formatted
    assert "{symbol}" not in formatted


@pytest.mark.parametrize(
    "model_name",
    ["typesafe/jev-1.13", "typesafe/jev-1.14"],
)
def test_jev_decision_model_selects_fibonacci_target_level(monkeypatch, model_name):
    import engine.llm as llm

    observed = {"requests": []}

    class MockResponse:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    responses = [
        {
            "answers": {
                "target_level": {
                    "choice": "level_5",
                    "probabilities": {
                        "level_1": 0.03,
                        "level_2": 0.04,
                        "level_3": 0.05,
                        "level_4": 0.06,
                        "level_5": 0.72,
                        "level_6": 0.04,
                        "level_7": 0.02,
                        "no_trade": 0.04,
                    },
                },
                "trade_success": {
                    "noul": 0.81,
                    "type": "noul",
                },
            },
            "usage": {"total_tokens": 12},
        },
    ]

    def fake_post(url, **kwargs):
        observed["url"] = url
        observed["requests"].append(kwargs)
        return MockResponse(responses[len(observed["requests"]) - 1])

    monkeypatch.setattr(llm, "API", "test-key")
    monkeypatch.setattr(llm, "TYPESAFE_API_KEY", None)
    monkeypatch.setattr(llm.requests, "post", fake_post)
    market_info = json.dumps({
        "market": {"current_price": 105.0},
        "price_history": [{"close": 105.0, "atr": 2.0}],
        "derived_features": {
            "fibonacci": {
                "status": "ok",
                "retracement_levels": {
                    "0": 110.0,
                    "0.236": 108.0,
                    "0.382": 107.0,
                    "0.5": 106.0,
                    "0.618": 105.5,
                    "0.786": 102.0,
                    "1": 100.0,
                },
            }
        },
    })

    response, usage = llm.inference(
        market_info,
        "BTCUSDT",
        "1h",
        model_name=model_name,
        prompt_text="Choose based on this state: {info}",
        scoring_horizon=12,
    )

    assert observed["url"] == llm.DECISION_API_URL
    assert observed["requests"][0]["headers"]["Authorization"] == "Bearer test-key"
    request_payload = observed["requests"][0]["json"]
    assert request_payload["model"] == model_name
    question = request_payload["questions"]["target_level"]
    assert question["type"] == "choice"
    assert len(question["criteria"]) == 8
    assert question["criteria"]["level_1"] == (
        "Fibonacci 0 retracement at price 110, above current price."
    )
    assert question["criteria"]["level_5"] == (
        "Fibonacci 0.618 retracement at price 105.5, above current price."
    )
    assert question["criteria"]["level_7"] == (
        "Fibonacci 1 retracement at price 100, below current price."
    )
    assert "derived_features" in request_payload["state"]
    success_question = request_payload["questions"]["trade_success"]
    assert success_question["type"] == "noul"
    assert "target_level" in success_question["instructions"]
    assert "within 12 candles" in success_question["criteria"]["true"]
    assert "within 12 candles" in success_question["criteria"]["false"]
    assert "level_5: scenario=up, target=105.5, stop-loss=102" in request_payload["state"]
    assert len(observed["requests"]) == 1
    assert response["scenario"] == "up"
    assert response["confidence"] == 0.72
    assert response["trade_success_probability"] == 0.81
    assert response["entry_price"] == 105.0
    assert response["target_price"] == 105.5
    assert response["stop_loss"] == 102.0
    assert response["analysis"] == ""
    assert response["target_fibonacci_level"] == "0.618"
    assert response["target_fibonacci_price"] == 105.5
    assert response["decision_probabilities"] == {
        "0": 0.03,
        "0.236": 0.04,
        "0.382": 0.05,
        "0.5": 0.06,
        "0.618": 0.72,
        "0.786": 0.04,
        "1": 0.02,
        "no_trade": 0.04,
    }
    assert usage == {"total_tokens": 12}

    observed["requests"].clear()
    llm.inference(
        market_info,
        "BTCUSDT",
        "1h",
        model_name=model_name,
        prompt_text="Choose based on this state: {info}",
    )
    assert len(observed["requests"]) == 1
    assert "trade_success" not in observed["requests"][0]["json"]["questions"]


@pytest.mark.parametrize("response_shape", ["answers", "typed_groups"])
@pytest.mark.parametrize(
    ("model_name", "typesafe_model"),
    [
        ("typesafe/jev-1.13", "jev-1.13.0"),
        ("typesafe/jev-1.14", "jev-1.14.0"),
    ],
)
def test_jev_can_use_direct_typesafe_sdk_without_openrouter(
    monkeypatch, response_shape, model_name, typesafe_model
):
    import engine.llm as llm
    import typesafe_sdk

    observed = {}
    Choice = typesafe_sdk.Choice
    Noul = typesafe_sdk.Noul

    class TypeSafeClient:
        def __init__(self, *, api_key, model):
            observed["api_key"] = api_key
            observed["model"] = model

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def system_one(self, *, state, questions):
            observed["state"] = state
            observed["questions"] = questions
            target_answer = SimpleNamespace(
                choice="level_1",
                confidence=0.72,
                probabilities={"level_1": 0.72, "no_trade": 0.28},
            )
            trade_success_answer = SimpleNamespace(noul=0.81)
            result = {
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
            if response_shape == "answers":
                result["answers"] = {
                    "target_level": target_answer,
                    "trade_success": trade_success_answer,
                }
            else:
                result["choices"] = {"target_level": target_answer}
                result["nouls"] = {"trade_success": trade_success_answer}
            return SimpleNamespace(**result)

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", TypeSafeClient)
    monkeypatch.setattr(llm, "TYPESAFE_API_KEY", "typesafe-test-key")
    monkeypatch.setattr(llm, "API", None)
    monkeypatch.setattr(
        llm.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("Direct TypeSafe calls must not use OpenRouter."),
    )
    monkeypatch.setattr(
        llm,
        "OpenAI",
        lambda **_kwargs: pytest.fail("Direct Jev calls must not initialize OpenRouter."),
    )

    response, usage = llm.inference(
        json.dumps({
            "market": {"current_price": 105.0},
            "price_history": [{"close": 105.0, "atr": 2.0}],
            "derived_features": {
                "fibonacci": {
                    "status": "ok",
                    "retracement_levels": {"0.618": 105.5, "0.786": 102.0},
                }
            },
        }),
        "BTCUSDT",
        "1h",
        model_name=model_name,
        prompt_text="Choose based on this state: {info}",
        scoring_horizon=12,
    )

    assert observed["api_key"] == "typesafe-test-key"
    assert observed["model"] == typesafe_model
    assert "derived_features" in observed["state"]
    assert isinstance(observed["questions"]["target_level"], Choice)
    assert isinstance(observed["questions"]["trade_success"], Noul)
    assert response["scenario"] == "up"
    assert response["target_fibonacci_level"] == "0.618"
    assert response["target_price"] == 105.5
    assert response["confidence"] == 0.72
    assert response["trade_success_probability"] == 0.81
    assert usage == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


@pytest.mark.parametrize(
    ("success_answer", "error"),
    [
        ({}, "missing answers.trade_success.noul"),
        ({"noul": 1.1, "type": "noul"}, "out-of-range trade-success probability"),
    ],
)
def test_jev_decision_model_rejects_invalid_native_success_probability(
    monkeypatch, success_answer, error
):
    import engine.llm as llm

    class MockResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "answers": {
                    "target_level": {
                        "choice": "no_trade",
                        "probabilities": {"no_trade": 1.0},
                    },
                    "trade_success": success_answer,
                }
            }

    observed = []

    def fake_post(url, **kwargs):
        observed.append(kwargs)
        return MockResponse()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm, "TYPESAFE_API_KEY", None)
    with pytest.raises(RuntimeError, match=error):
        llm.inference(
            json.dumps({
                "market": {"current_price": 100.0},
                "derived_features": {"fibonacci": {"status": "ok", "retracement_levels": {}}},
            }),
            "BTCUSDT",
            "1h",
            model_name="typesafe/jev-1.13",
            prompt_text="Choose based on this state: {info}",
            scoring_horizon=12,
        )
    assert len(observed) == 1


def test_default_skill_adds_shared_market_analysis_guidance():
    instructions = load_skill_instructions("default")

    assert "consider all relevant context" in instructions
    assert "Do not invent" in instructions
    assert "Follow the selected prompt" in instructions
    assert '"scenario"' not in instructions


def test_project_skills_are_additive_instruction_only():
    assert "risk_first" in available_skills()
    assert "market_structure" in available_skills()
    instructions = load_skill_instructions("risk_first")
    assert "capital preservation" in instructions
    assert '"scenario"' not in instructions


def test_skill_is_appended_without_replacing_base_prompt():
    base = "Required JSON format: {info}"
    formatted = format_inference_prompt(
        "market data",
        "BTCUSDT",
        "1h",
        prompt_text=base,
        skill_instructions="Prefer conservative decisions.",
    )

    assert "Required JSON format: market data" in formatted
    assert "Supplemental skill instructions" in formatted
    assert "Prefer conservative decisions." in formatted


def test_preprocessors_append_features_and_preserve_fetched_context():
    market_data = {
        "market": {"symbol": "BTCUSDT", "current_price": 105.0},
        "price_history": [
            {"time": "now", "open": 101.0, "high": 110.0, "low": 100.0, "close": 105.0},
            {"time": "past", "open": 99.0, "high": 105.0, "low": 95.0, "close": 102.0},
        ],
        "web_context": {
            "context": "Market news context",
            "results": [{"title": "Headline", "url": "https://example.com"}],
        },
        "higher_timeframes": {"4h": {"price_history": [{"close": 103.0}]}},
    }

    processed = apply_preprocessors(market_data, ["fibonacci", "none"])

    assert processed["market"] == market_data["market"]
    assert processed["price_history"] == market_data["price_history"]
    assert processed["web_context"] == market_data["web_context"]
    assert processed["higher_timeframes"] == market_data["higher_timeframes"]
    assert "0.618" in processed["derived_features"]["fibonacci"]["retracement_levels"]
    assert "derived_features" not in market_data


def test_preprocessor_receives_market_payload_built_for_inference():
    candles = pd.DataFrame([
        {"time": "2026-01-01 00:00:00", "open": 100, "high": 105, "low": 99, "close": 104, "volume": 10},
        {"time": "2026-01-01 01:00:00", "open": 104, "high": 111, "low": 102, "close": 108, "volume": 12},
    ])
    snapshot = {
        "spread": 0.1,
        "orderbook_imbalance": 0.2,
        "bid_volume": 4.0,
        "ask_volume": 3.0,
        "buy_volume": 2.0,
        "sell_volume": 1.0,
        "buy_sell_ratio": 2.0,
        "trade_count": 3,
        "volatility": 0.01,
        "price": 108.0,
    }
    news = {
        "symbol": "BTCUSDT",
        "query": "BTC news",
        "context": "Market-moving headline",
        "results": [{"title": "Headline", "url": "https://example.com"}],
    }

    raw_payload = json.loads(build_llm_market_input(
        "BTCUSDT",
        "1h",
        candles,
        snapshot=snapshot,
        web_data=news,
        quant_data={"target_mode": "percentage_return"},
        n=2,
    ))
    processed = apply_preprocessors(raw_payload, ["fibonacci"])

    assert processed["market"]["current_price"] == 108.0
    assert processed["market_microstructure"]["orderbook_imbalance"] == 0.2
    assert processed["trade_flow"]["buy_sell_ratio"] == 2.0
    assert processed["volatility"] == 0.01
    assert processed["price_history"][0]["time"] == "2026-01-01 01:00:00"
    assert processed["quant"] == {"target_mode": "percentage_return"}
    assert processed["web_context"]["results"] == news["results"]
    assert processed["derived_features"]["fibonacci"]["status"] == "ok"


def test_noop_preprocessor_leaves_market_data_unchanged():
    market_data = {"market": {"current_price": 100}, "price_history": []}

    assert apply_preprocessors(market_data, ["none"]) == market_data


def test_signal_validation_rejects_invalid_scenarios():
    with pytest.raises(ValueError, match="scenario must be"):
        validate_inference_result({"scenario": "hold"})


def test_signal_validation_rejects_invalid_trade_success_probability():
    with pytest.raises(ValueError, match="trade_success_probability"):
        validate_inference_result({
            "scenario": "up",
            "confidence": 0.8,
            "trade_success_probability": 1.1,
            "entry_price": 100,
            "target_price": 110,
            "stop_loss": 95,
            "expected_time": 3,
            "analysis": "test",
        })


def test_model_plugin_keeps_existing_inference_and_applies_skill(monkeypatch):
    import plugins.model as model_plugin

    observed = {}

    def fake_inference(info, symbol, time_frame, **kwargs):
        observed.update(kwargs)
        return ({
            "scenario": "no_trade",
            "confidence": 0.1,
            "entry_price": 10,
            "target_price": 10,
            "stop_loss": 10,
            "expected_time": 1,
            "analysis": "Test",
        }, None)

    monkeypatch.setattr(model_plugin, "inference", fake_inference)
    response, _ = run_inference(
        "model",
        "{}",
        "BTCUSDT",
        "1h",
        skill_name="risk_first",
    )

    assert observed["prompt_text"] is None
    assert observed["skill_instructions"] == load_skill_instructions("risk_first")
    assert response["scenario"] == "no_trade"
