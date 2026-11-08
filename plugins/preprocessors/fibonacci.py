"""Derive Fibonacci retracement levels from the visible candle window."""

from __future__ import annotations

from typing import Any

from plugins.preprocessing import PreprocessingPlugin

RETRACEMENT_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


class FibonacciPreprocessor(PreprocessingPlugin):
    """Calculate retracement levels from high/low values in supplied price history."""

    def transform(self, market_data: dict[str, Any]) -> dict[str, Any]:
        candles = market_data.get("price_history")
        if not isinstance(candles, list) or not candles:
            return {"status": "unavailable", "reason": "price_history is empty"}

        valid_candles = []
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            try:
                high = float(candle["high"])
                low = float(candle["low"])
            except (KeyError, TypeError, ValueError):
                continue
            if high >= low:
                valid_candles.append((high, low))

        if not valid_candles:
            return {"status": "unavailable", "reason": "no valid candle high/low values"}

        swing_high = max(high for high, _ in valid_candles)
        swing_low = min(low for _, low in valid_candles)
        price_range = swing_high - swing_low
        if price_range <= 0:
            return {"status": "unavailable", "reason": "visible candle range is zero"}

        levels = {
            f"{ratio:.3f}".rstrip("0").rstrip("."): swing_high - price_range * ratio
            for ratio in RETRACEMENT_RATIOS
        }
        result: dict[str, Any] = {
            "status": "ok",
            "window_candles": len(valid_candles),
            "swing_low": swing_low,
            "swing_high": swing_high,
            "retracement_levels": levels,
        }
        current_price = (market_data.get("market") or {}).get("current_price")
        if current_price is None:
            current_price = candles[0].get("close") if isinstance(candles[0], dict) else None
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            return result
        nearest_ratio, nearest_level = min(
            levels.items(),
            key=lambda item: abs(item[1] - current_price),
        )
        result["current_price"] = current_price
        result["nearest_level"] = {
            "ratio": float(nearest_ratio),
            "price": nearest_level,
            "distance_pct": (nearest_level - current_price) / current_price * 100
            if current_price
            else None,
        }
        return result
