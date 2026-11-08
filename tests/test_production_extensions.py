import pytest

from plugins.preprocessor_registry import BUILTIN_PREPROCESSORS, load_preprocessor
from plugins.registry import BUILTIN_PLUGINS, load_inference_plugin


def test_model_is_the_only_builtin_inference_plugin():
    assert set(BUILTIN_PLUGINS) == {"model"}
    assert "llm" not in BUILTIN_PLUGINS
    assert "quant" not in BUILTIN_PLUGINS
    assert "structure" not in BUILTIN_PLUGINS
    for removed_plugin in ("quant", "structure"):
        with pytest.raises(ValueError, match="Unknown inference plugin"):
            load_inference_plugin(removed_plugin)
    assert set(BUILTIN_PREPROCESSORS) == {"none", "fibonacci", "price_change"}
    for removed_preprocessor in ("candlestick", "market_structure", "volatility_regime"):
        with pytest.raises(ValueError, match="Unknown preprocessor"):
            load_preprocessor(removed_preprocessor)
