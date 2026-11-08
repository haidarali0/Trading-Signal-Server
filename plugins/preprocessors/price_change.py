"""Generate fixed percentage-change price levels around the current price."""

from __future__ import annotations

import math
from typing import Any

from plugins.preprocessing import PreprocessingPlugin

CHANGE_PERCENTAGES = (20, 40, 60, 80, 100)


class PriceChangePreprocessor(PreprocessingPlugin):
    """Create symmetric percentage price targets from the current market price."""

    def transform(self, market_data: dict[str, Any]) -> dict[str, Any]:
        market = market_data.get("market")
        current_price = market.get("current_price") if isinstance(market, dict) else None
        price_source = "market.current_price"

        if current_price is None:
            candles = market_data.get("price_history")
            latest = candles[0] if isinstance(candles, list) and candles else None
            current_price = latest.get("close") if isinstance(latest, dict) else None
            price_source = "price_history[0].close"

        if isinstance(current_price, bool):
            return {
                "status": "unavailable",
                "reason": "current price must be a finite positive number",
            }
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            return {
                "status": "unavailable",
                "reason": "current price is missing or not numeric",
            }
        if not math.isfinite(current_price) or current_price <= 0:
            return {
                "status": "unavailable",
                "reason": "current price must be a finite positive number",
            }

        changes = [0, *(value for step in CHANGE_PERCENTAGES for value in (step, -step))]
        levels = {}
        for change_percent in changes:
            target_price = current_price * (1.0 + change_percent / 100.0)
            label = f"{change_percent:+d}%" if change_percent else "0%"
            levels[label] = {
                "change_percent": change_percent,
                "price": target_price,
                "direction": "up" if change_percent > 0 else "down" if change_percent < 0 else "unchanged",
                "usable": target_price > 0,
            }

        return {
            "status": "ok",
            "anchor_price": current_price,
            "anchor_source": price_source,
            "levels": levels,
        }
