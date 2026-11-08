"""Load and run configured market-data preprocessing plugins."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any

from .preprocessing import PreprocessingPlugin

BUILTIN_PREPROCESSORS = {
    "none": ("plugins.preprocessors.noop", "NoOpPreprocessor"),
    "fibonacci": ("plugins.preprocessors.fibonacci", "FibonacciPreprocessor"),
    "price_change": (
        "plugins.preprocessors.price_change",
        "PriceChangePreprocessor",
    ),
}


def load_preprocessor(name: str) -> PreprocessingPlugin:
    """Load a built-in preprocessor or a ``module.path:ClassName`` implementation."""
    plugin_name = str(name or "").strip()
    if plugin_name in BUILTIN_PREPROCESSORS:
        module_name, class_name = BUILTIN_PREPROCESSORS[plugin_name]
    elif ":" in plugin_name:
        module_name, class_name = plugin_name.rsplit(":", 1)
        if not module_name or not class_name:
            raise ValueError("Custom preprocessor must use the format module.path:ClassName.")
    else:
        raise ValueError(
            f"Unknown preprocessor '{plugin_name}'. Use 'none', 'fibonacci', "
            "'price_change', "
            "or a module.path:ClassName reference."
        )

    module = import_module(module_name)
    plugin_type = getattr(module, class_name, None)
    if not isinstance(plugin_type, type) or not issubclass(plugin_type, PreprocessingPlugin):
        raise TypeError(
            f"Preprocessor '{plugin_name}' must derive from PreprocessingPlugin."
        )
    return plugin_type()


def apply_preprocessors(
    market_data: dict[str, Any],
    preprocessor_names: list[str] | None = None,
) -> dict[str, Any]:
    """Append each preprocessor's output under ``derived_features``."""
    if not isinstance(market_data, dict):
        raise TypeError("Preprocessors require a market-data object.")

    names = preprocessor_names or ["none"]
    if len(set(names)) != len(names):
        raise ValueError("Preprocessor names must not contain duplicates.")

    result = deepcopy(market_data)
    derived_features = dict(result.get("derived_features") or {})
    for name in names:
        preprocessor = load_preprocessor(name)
        features = preprocessor.transform(deepcopy(result))
        if not isinstance(features, dict):
            raise TypeError(f"Preprocessor '{name}' must return a dictionary.")
        if features:
            feature_key = name.rsplit(":", 1)[-1] if ":" in name else name
            derived_features[feature_key] = features

    if derived_features:
        result["derived_features"] = derived_features
    return result
