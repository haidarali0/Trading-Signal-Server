"""Shared contract for inference plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class InferenceRequest:
    market_info: str
    symbol: str
    time_frame: str
    web_context: str | None = None
    model_name: str | None = None
    prompt_text: str | None = None
    skill_name: str = "default"
    scoring_horizon: int | None = None


class InferencePlugin(ABC):
    """Implement this interface to add an inference backend."""

    @abstractmethod
    def infer(self, request: InferenceRequest) -> tuple[dict[str, Any], Any]:
        """Return a signal payload and optional usage information."""


def validate_inference_result(value: Any) -> dict[str, Any]:
    """Validate and normalize the signal fields shared by live and backtest runs."""
    if not isinstance(value, dict):
        raise ValueError("Inference plugin must return a dictionary signal.")

    result = dict(value)
    scenario = str(result.get("scenario", "")).strip().lower()
    if scenario not in {"up", "down", "no_trade"}:
        raise ValueError("Inference result scenario must be up, down, or no_trade.")
    result["scenario"] = scenario

    for field in ("entry_price", "target_price", "stop_loss", "confidence", "expected_time"):
        raw_value = result.get(field)
        if isinstance(raw_value, bool):
            raise ValueError(f"Inference result field '{field}' must be numeric.")
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Inference result field '{field}' must be numeric.") from exc
        if not math.isfinite(numeric_value):
            raise ValueError(f"Inference result field '{field}' must be finite.")
        result[field] = numeric_value

    if result["entry_price"] <= 0:
        raise ValueError("Inference result entry_price must be greater than zero.")
    if not 0 <= result["confidence"] <= 1:
        raise ValueError("Inference result confidence must be between 0 and 1.")
    if result["expected_time"] <= 0:
        raise ValueError("Inference result expected_time must be greater than zero.")
    result["expected_time"] = max(1, int(round(result["expected_time"])))

    if result.get("trade_success_probability") is not None:
        raw_probability = result["trade_success_probability"]
        if isinstance(raw_probability, bool):
            raise ValueError("Inference result trade_success_probability must be numeric.")
        try:
            probability = float(raw_probability)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Inference result trade_success_probability must be numeric."
            ) from exc
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError(
                "Inference result trade_success_probability must be finite and between 0 and 1."
            )
        result["trade_success_probability"] = probability

    if not isinstance(result.get("analysis"), str):
        raise ValueError("Inference result analysis must be a string.")
    return result
