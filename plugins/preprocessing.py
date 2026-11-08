"""Shared contract for market-data preprocessing plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PreprocessingPlugin(ABC):
    """Derive inference features from the normalized market-data payload."""

    @abstractmethod
    def transform(self, market_data: dict[str, Any]) -> dict[str, Any]:
        """Return JSON-serializable derived features without replacing source data."""
