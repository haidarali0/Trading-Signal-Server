"""Load built-in and user-defined inference plugins."""

from __future__ import annotations

from importlib import import_module

from .base import InferencePlugin

BUILTIN_PLUGINS = {
    "model": ("plugins.model", "ModelInferencePlugin"),
}


def load_inference_plugin(name: str) -> InferencePlugin:
    """Load a built-in plugin name or a ``module.path:ClassName`` plugin."""
    plugin_name = str(name or "").strip()
    if plugin_name in BUILTIN_PLUGINS:
        module_name, class_name = BUILTIN_PLUGINS[plugin_name]
    elif ":" in plugin_name:
        module_name, class_name = plugin_name.rsplit(":", 1)
        if not module_name or not class_name:
            raise ValueError("Custom plugin must use the format module.path:ClassName.")
    else:
        raise ValueError(
            f"Unknown inference plugin '{plugin_name}'. Use 'model' or a "
            "module.path:ClassName reference."
        )

    module = import_module(module_name)
    plugin_type = getattr(module, class_name, None)
    if not isinstance(plugin_type, type) or not issubclass(plugin_type, InferencePlugin):
        raise TypeError(f"Plugin '{plugin_name}' must be a class derived from InferencePlugin.")
    return plugin_type()
