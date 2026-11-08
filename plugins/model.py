"""Model inference plugin for configured GenAI and typed decision models."""

from __future__ import annotations

from typing import Any

from engine.llm import inference
from skills import load_skill_instructions

from .base import InferencePlugin, InferenceRequest


class ModelInferencePlugin(InferencePlugin):
    """Route configured models through the project's provider-aware inference."""

    def infer(self, request: InferenceRequest) -> tuple[dict[str, Any], Any]:
        skill_instructions = load_skill_instructions(request.skill_name)
        response, usage = inference(
            request.market_info,
            request.symbol,
            request.time_frame,
            web_context=request.web_context,
            model_name=request.model_name,
            prompt_text=request.prompt_text,
            skill_instructions=skill_instructions,
            scoring_horizon=request.scoring_horizon,
        )
        response.setdefault("model_name", request.model_name or "model")
        return response, usage
