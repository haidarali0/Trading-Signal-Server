import numpy as np
import pandas as pd

from quant import QuantConfig, available_target_modes, build_target, run_quant_models


def sample_candles(rows=12):
    close = pd.Series(np.arange(100.0, 100.0 + rows))
    return pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.arange(1.0, rows + 1),
    })


def test_all_target_modes_have_forward_aligned_values():
    candles = sample_candles()

    assert set(available_target_modes()) == {
        "raw_price", "percentage_return", "log_return",
        "binary_direction", "ternary_direction", "future_volatility",
    }
    assert build_target(candles, "raw_price", 1).iloc[0] == 101.0
    assert np.isclose(build_target(candles, "percentage_return", 1).iloc[0], 0.01)
    assert build_target(candles, "binary_direction", 1).iloc[0] == 1.0
    assert build_target(candles, "ternary_direction", 1).iloc[0] == 1.0
    assert build_target(candles, "raw_price", 1).iloc[-1] != build_target(candles, "raw_price", 1).iloc[-1]
    volatility = build_target(candles, "future_volatility", 1)
    assert volatility.iloc[0] > 0
    assert volatility.iloc[-1] != volatility.iloc[-1]


def test_parallel_models_return_normalized_outputs_and_ensemble():
    rows = 40
    X = pd.DataFrame({"feature_a": np.arange(rows), "feature_b": np.arange(rows) % 3})
    y = pd.Series(np.arange(rows, dtype=float))
    result = run_quant_models(
        X,
        y,
        QuantConfig(model_families={"regression": ["ridge", "extra_trees"]}),
        predict_rows=2,
    )

    assert result["target_mode"] == "raw_price"
    assert result["horizon"] == 1
    assert [item["model"] for item in result["models"]] == ["extra_trees", "ridge"]
    assert all("metrics" in item and "predictions" in item for item in result["models"])
    assert all("baseline_mae" in item["metrics"] and "reliability" in item["metrics"] for item in result["models"])
    assert result["ensembles"][0]["model_count"] == 2
    assert result["selected"]["family"] == "regression"
    assert result["reliable"] is True


def test_classification_models_produce_direction_and_confidence():
    rows = 50
    X = pd.DataFrame({"feature_a": np.arange(rows), "feature_b": np.arange(rows) % 4})
    y = pd.Series((np.arange(rows) % 2).astype(float))
    result = run_quant_models(
        X,
        y,
        QuantConfig(target_mode="binary_direction", model_families={"classification": ["logistic_regression"]}),
    )

    model = result["models"][0]
    assert model["family"] == "classification"
    assert model["direction"] is not None
    assert model["confidence"] is not None
    assert "accuracy" in model["metrics"]