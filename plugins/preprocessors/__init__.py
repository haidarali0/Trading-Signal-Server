"""Built-in market-data preprocessing plugins."""

from .fibonacci import FibonacciPreprocessor
from .noop import NoOpPreprocessor
from .price_change import PriceChangePreprocessor

__all__ = ["FibonacciPreprocessor", "NoOpPreprocessor", "PriceChangePreprocessor"]
