"""Training, evaluation, and prediction helpers for regressors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency
    class _TqdmFallback:
# Function: __init__
# Function: __init__
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

# Function: __enter__
        def __enter__(self):
            return self

# Function: __exit__
        def __exit__(self, exc_type, exc, tb):
            return False

# Function: update
        def update(self, n=1):
            return None

# Function: tqdm
    def tqdm(*args, **kwargs):
        return _TqdmFallback(*args, **kwargs)

from .model_zoo import get_model


@dataclass
class TrainingResult:
    model: Any
    X_train: Any
    X_test: Any
    y_train: Any
    y_test: Any
    metrics: dict[str, float]


# Function: train_regressor
def train_regressor(
    X,
    y,
    model_name: str = "random_forest",
    model_params: dict | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    shuffle: bool = False,
) -> TrainingResult:
    """Train a regression model and return the fitted model plus dataset splits."""
    # For time-series data we prefer a chronological split (no shuffling).
    if not shuffle:
        # Preserve index ordering if DataFrame/Series
        try:
            n = len(X)
            split = int(n * (1.0 - test_size))
            X_train = X.iloc[:split]
            X_test = X.iloc[split:]
            y_train = y.iloc[:split]
            y_test = y.iloc[split:]
        except Exception:
            # Fallback to train_test_split if indexing fails
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=random_state, shuffle=False
            )
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, shuffle=shuffle
        )
    model = get_model(model_name, model_params=model_params, random_state=random_state)
    print(
        f"[Quant] training {model_name} on {len(X_train)} rows, testing on {len(X_test)} rows"
    )
    with tqdm(total=1, desc=f"Fitting {model_name}") as pbar:
        model.fit(X_train, y_train)
        pbar.update(1)
    y_pred = model.predict(X_test)
    metrics = evaluate_regression(y_test, y_pred)
    print(
        f"[Quant] fit complete | MAE: {metrics['mean_absolute_error']:.4f}, "
        f"MSE: {metrics['mean_squared_error']:.4f}, R²: {metrics['r2_score']:.4f}"
    )
    return TrainingResult(
        model=model,
        X_train=X_train,
        X_test=X_test,
        y_train=y_train,
        y_test=y_test,
        metrics=metrics,
    )


# Function: evaluate_regression
def evaluate_regression(y_true, y_pred) -> dict[str, float]:
    """Evaluate regression predictions using common metrics."""
    y_true_arr = np.array(y_true).ravel()
    y_pred_arr = np.array(y_pred).ravel()
    return {
        "mean_squared_error": float(mean_squared_error(y_true_arr, y_pred_arr)),
        "mean_absolute_error": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "r2_score": float(r2_score(y_true_arr, y_pred_arr)),
    }


# Function: train_regressor_and_report
def train_regressor_and_report(
    X,
    y,
    model_name: str = "random_forest",
    model_params: dict | None = None,
    test_size: float = 0.2,
    random_state: int = 42,
    shuffle: bool = True,
) -> TrainingResult:
    """Train the model and return training metrics and fitted model."""
    result = train_regressor(
        X,
        y,
        model_name=model_name,
        model_params=model_params,
        test_size=test_size,
        random_state=random_state,
        shuffle=shuffle,
    )
    return result


# Function: predict_with_model
def predict_with_model(model, X):
    """Generate predictions from a trained model."""
    return model.predict(X)
