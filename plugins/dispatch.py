"""Dispatch inference requests to a configured plugin."""

from __future__ import annotations

from typing import Any

from .base import InferenceRequest, validate_inference_result
from .registry import load_inference_plugin


def run_inference(
    plugin_name: str,
    market_info: str,
    symbol: str,
    time_frame: str,
    web_context: str | None = None,
    model_name: str | None = None,
    prompt_text: str | None = None,
    skill_name: str = "default",
    scoring_horizon: int | None = None,
) -> tuple[dict[str, Any], Any]:
    """Run and validate one inference request through the selected plugin."""
    plugin = load_inference_plugin(plugin_name)
    request = InferenceRequest(
        market_info=market_info,
        symbol=symbol,
        time_frame=time_frame,
        web_context=web_context,
        model_name=model_name,
        prompt_text=prompt_text,
        skill_name=skill_name,
        scoring_horizon=scoring_horizon,
    )
    response, usage = plugin.infer(request)
    return validate_inference_result(response), usage
