"""Registry of supported regression models."""

from __future__ import annotations

from typing import Any, Dict

try:
    from sklearn.ensemble import (
        ExtraTreesRegressor,
        GradientBoostingRegressor,
        HistGradientBoostingRegressor,
        RandomForestRegressor,
    )
    from sklearn.linear_model import Ridge
    from sklearn.linear_model import SGDRegressor, PassiveAggressiveRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.svm import SVR
    from sklearn.ensemble import (
        ExtraTreesClassifier,
        GradientBoostingClassifier,
        HistGradientBoostingClassifier,
        RandomForestClassifier,
    )
    from sklearn.linear_model import LogisticRegression
except ImportError as exc:
    raise ImportError(
        "scikit-learn is required for quant regressors. Install it with `pip install scikit-learn`."
    ) from exc

MODEL_REGISTRY: Dict[str, Any] = {
    "random_forest": RandomForestRegressor,
    "extra_trees": ExtraTreesRegressor,
    "gradient_boosting": GradientBoostingRegressor,
    "hist_gradient_boosting": HistGradientBoostingRegressor,
    "k_neighbors": KNeighborsRegressor,
    "ridge": Ridge,
    "svr": SVR,
    "sgd": SGDRegressor,
    "passive_aggressive": PassiveAggressiveRegressor,
}

CLASSIFIER_REGISTRY: Dict[str, Any] = {
    "random_forest": RandomForestClassifier,
    "extra_trees": ExtraTreesClassifier,
    "gradient_boosting": GradientBoostingClassifier,
    "hist_gradient_boosting": HistGradientBoostingClassifier,
    "logistic_regression": LogisticRegression,
}


# Function: available_models
def available_models() -> list[str]:
    """Return the list of supported model names."""
    return sorted(MODEL_REGISTRY.keys())


# Function: get_model
def get_model(model_name: str, model_params: dict | None = None, random_state: int | None = None):
    """Create a new regressor instance by name."""
    model_name = model_name.lower()
    if model_name not in MODEL_REGISTRY:
        raise ValueError(
            f"Unsupported model '{model_name}'. Available models: {', '.join(available_models())}"
        )

    model_cls = MODEL_REGISTRY[model_name]
    params = dict(model_params or {})
    if random_state is not None:
        try:
            import inspect

            signature = inspect.signature(model_cls.__init__)
            if "random_state" in signature.parameters:
                params.setdefault("random_state", random_state)
        except (TypeError, ValueError):
            pass
    return model_cls(**params)


def available_classifiers() -> list[str]:
    return sorted(CLASSIFIER_REGISTRY.keys())


def get_classifier(model_name: str, model_params: dict | None = None, random_state: int | None = None):
    """Create a classifier using the same naming and random-state conventions."""
    name = model_name.lower()
    if name not in CLASSIFIER_REGISTRY:
        raise ValueError(f"Unsupported classifier '{name}'. Available: {', '.join(available_classifiers())}")
    model_cls = CLASSIFIER_REGISTRY[name]
    params = dict(model_params or {})
    if random_state is not None:
        import inspect
        if "random_state" in inspect.signature(model_cls.__init__).parameters:
            params.setdefault("random_state", random_state)
    return model_cls(**params)
