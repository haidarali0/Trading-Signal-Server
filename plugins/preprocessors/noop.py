"""Default preprocessor, which leaves fetched market data unchanged."""

from __future__ import annotations

from typing import Any

from plugins.preprocessing import PreprocessingPlugin


class NoOpPreprocessor(PreprocessingPlugin):
    """Leave the market payload unchanged by returning no derived features."""

    def transform(self, market_data: dict[str, Any]) -> dict[str, Any]:
        return {}
