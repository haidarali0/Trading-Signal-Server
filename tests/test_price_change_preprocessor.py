from plugins import apply_preprocessors
from plugins.preprocessors.price_change import PriceChangePreprocessor


def test_price_change_preprocessor_generates_signed_percentage_targets():
    result = PriceChangePreprocessor().transform({
        "market": {"current_price": 1000.0},
    })

    assert result["status"] == "ok"
    assert result["anchor_price"] == 1000.0
    assert result["anchor_source"] == "market.current_price"
    assert len(result["levels"]) == 11
    assert result["levels"]["0%"] == {
        "change_percent": 0,
        "price": 1000.0,
        "direction": "unchanged",
        "usable": True,
    }
    assert result["levels"]["+20%"]["price"] == 1200.0
    assert result["levels"]["-20%"]["price"] == 800.0
    assert result["levels"]["+100%"]["price"] == 2000.0
    assert result["levels"]["-100%"] == {
        "change_percent": -100,
        "price": 0.0,
        "direction": "down",
        "usable": False,
    }


def test_price_change_preprocessor_falls_back_to_latest_candle_close():
    result = PriceChangePreprocessor().transform({
        "price_history": [{"close": 250.0}],
    })

    assert result["status"] == "ok"
    assert result["anchor_price"] == 250.0
    assert result["anchor_source"] == "price_history[0].close"
    assert result["levels"]["+20%"]["price"] == 300.0


def test_price_change_preprocessor_reports_missing_or_invalid_anchor():
    preprocessor = PriceChangePreprocessor()

    assert preprocessor.transform({})["status"] == "unavailable"
    assert preprocessor.transform({
        "market": {"current_price": float("nan")},
    })["status"] == "unavailable"


def test_price_change_plugin_adds_features_without_mutating_market_input():
    market_data = {
        "market": {"current_price": 50.0},
        "price_history": [{"close": 49.0}],
    }

    processed = apply_preprocessors(market_data, ["price_change"])

    assert processed["derived_features"]["price_change"]["levels"]["+20%"]["price"] == 60.0
    assert "derived_features" not in market_data
