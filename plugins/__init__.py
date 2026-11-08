"""Inference plugin interfaces and built-in plugin loading."""

from .base import InferencePlugin, InferenceRequest, validate_inference_result
from .preprocessing import PreprocessingPlugin
from .preprocessor_registry import apply_preprocessors, load_preprocessor
from .registry import load_inference_plugin
from .selection import decision_model_setup_warning, format_extension_selection

__all__ = [
    "InferencePlugin",
    "InferenceRequest",
    "PreprocessingPlugin",
    "apply_preprocessors",
    "decision_model_setup_warning",
    "format_extension_selection",
    "load_preprocessor",
    "load_inference_plugin",
    "validate_inference_result",
]
