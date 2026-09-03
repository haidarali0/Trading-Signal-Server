"""Unified, parallel execution for quantitative model families."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error, r2_score

from .model_zoo import get_classifier, get_model


@dataclass
class QuantConfig:
    target_mode: str = "raw_price"
    horizon: int = 1
    direction_threshold: float = 0.001
    model_families: dict[str, list[str]] = field(default_factory=lambda: {"regression": ["random_forest"]})
    test_size: float = 0.2
    random_state: int = 42
    max_workers: int | None = None
    validation_folds: int = 3
    exclude_unreliable: bool = True
    minimum_reliability: float = 0.0

    def normalized(self) -> "QuantConfig":
        families = {
            str(family): list(dict.fromkeys(str(name).lower() for name in names if str(name).strip()))
            for family, names in self.model_families.items()
        }
        return QuantConfig(
            target_mode=self.target_mode,
            horizon=self.horizon,
            direction_threshold=self.direction_threshold,
            model_families={key: value for key, value in families.items() if value},
            test_size=self.test_size,
            random_state=self.random_state,
            max_workers=self.max_workers,
            validation_folds=max(1, self.validation_folds),
            exclude_unreliable=self.exclude_unreliable,
            minimum_reliability=self.minimum_reliability,
        )


def _split(X, y, test_size: float):
    split = int(len(X) * (1.0 - test_size))
    if split < 1 or split >= len(X):
        raise ValueError("Quant dataset is too small for the configured test size.")
    return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]


def _walk_forward_splits(X, y, test_size: float, folds: int):
    test_length = max(1, int(len(X) * test_size))
    first_test = len(X) - test_length * folds
    if first_test < 1:
        folds = max(1, (len(X) - 1) // test_length)
        first_test = len(X) - test_length * folds
    for fold in range(folds):
        test_start = first_test + fold * test_length
        test_end = min(len(X), test_start + test_length)
        if test_start > 0 and test_start < test_end:
            yield X.iloc[:test_start], X.iloc[test_start:test_end], y.iloc[:test_start], y.iloc[test_start:test_end]


def _fit_one(family: str, name: str, X_train, y_train, X_test, y_test, X_predict, config: QuantConfig) -> dict[str, Any]:
    is_classification = family == "classification" or config.target_mode in {"binary_direction", "ternary_direction"}
    model = get_classifier(name, random_state=config.random_state) if is_classification else get_model(name, random_state=config.random_state)
    model.fit(X_train, y_train)
    predictions = np.asarray(model.predict(X_predict))
    test_predictions = np.asarray(model.predict(X_test))
    validation_predictions = []
    validation_actual = []
    fold_scores = []
    for fold_X_train, fold_X_test, fold_y_train, fold_y_test in _walk_forward_splits(
        X_train, y_train, config.test_size, config.validation_folds
    ):
        fold_model = get_classifier(name, random_state=config.random_state) if is_classification else get_model(name, random_state=config.random_state)
        fold_model.fit(fold_X_train, fold_y_train)
        fold_prediction = np.asarray(fold_model.predict(fold_X_test))
        validation_predictions.extend(fold_prediction.tolist())
        validation_actual.extend(fold_y_test.tolist())
        if is_classification:
            fold_scores.append(float(accuracy_score(fold_y_test, fold_prediction)))
        else:
            fold_scores.append(float(mean_absolute_error(fold_y_test, fold_prediction)))
    if not validation_predictions:
        validation_predictions = test_predictions.tolist()
        validation_actual = y_test.tolist()
    if is_classification:
        validation_predictions_array = np.asarray(validation_predictions)
        validation_actual_array = np.asarray(validation_actual)
        majority = np.full_like(validation_actual_array, _majority_class(y_train))
        model_accuracy = float(accuracy_score(validation_actual_array, validation_predictions_array))
        baseline_accuracy = float(accuracy_score(validation_actual_array, majority))
        metrics = {
            "accuracy": model_accuracy,
            "baseline_accuracy": baseline_accuracy,
            "stability": float(1.0 - np.std(fold_scores) if fold_scores else 1.0),
        }
        probabilities = getattr(model, "predict_proba", lambda values: None)(X_predict)
        confidence = float(np.max(probabilities, axis=1).mean()) if probabilities is not None else None
        directions = [int(value) for value in predictions]
        reliability = model_accuracy - baseline_accuracy
    else:
        validation_predictions_array = np.asarray(validation_predictions)
        validation_actual_array = np.asarray(validation_actual)
        baseline_value = float(np.mean(y_train))
        baseline_predictions = np.full(len(validation_actual_array), baseline_value)
        model_mae = float(mean_absolute_error(validation_actual_array, validation_predictions_array))
        baseline_mae = float(mean_absolute_error(validation_actual_array, baseline_predictions))
        metrics = {
            "mean_absolute_error": model_mae,
            "mean_squared_error": float(mean_squared_error(validation_actual_array, validation_predictions_array)),
            "r2_score": float(r2_score(validation_actual_array, validation_predictions_array)),
            "baseline_mae": baseline_mae,
            "baseline_mse": float(mean_squared_error(validation_actual_array, baseline_predictions)),
            "stability": float(1.0 - np.std(fold_scores) / (np.mean(fold_scores) + 1e-12) if fold_scores else 1.0),
        }
        confidence = float(np.clip(1.0 - model_mae / (np.std(validation_actual_array) + 1e-12), 0.0, 1.0))
        directions = None
        reliability = 1.0 - model_mae / (baseline_mae + 1e-12)
    metrics["reliability"] = float(reliability)
    metrics["accepted"] = bool(reliability > config.minimum_reliability) if config.exclude_unreliable else True
    return {
        "model": name,
        "family": family,
        "target_mode": config.target_mode,
        "horizon": config.horizon,
        "predictions": [value.item() if hasattr(value, "item") else value for value in predictions],
        "direction": directions,
        "confidence": confidence,
        "metrics": metrics,
    }


def _majority_class(values) -> Any:
    unique, counts = np.unique(values, return_counts=True)
    return unique[int(np.argmax(counts))]


def _ensemble(outputs: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    members = [item for item in outputs if item["family"] == family and item["metrics"].get("accepted", True)]
    if not members:
        return None
    predictions = [item["predictions"] for item in members]
    weights = np.asarray([max(0.0, item["metrics"].get("reliability", 0.0)) for item in members])
    if not weights.any():
        return None
    combined = np.average(predictions, axis=0, weights=weights).tolist()
    result = {
        "family": family,
        "model_count": len(members),
        "predictions": combined,
        "reliability": float(np.average([item["metrics"].get("reliability", 0.0) for item in members], weights=weights)),
        "models": [item["model"] for item in members],
    }
    if all(item.get("direction") is not None for item in members):
        result["direction"] = [int(round(value)) for value in np.mean([item["direction"] for item in members], axis=0)]
    confidences = [item["confidence"] for item in members if item.get("confidence") is not None]
    if confidences:
        result["confidence"] = float(np.mean(confidences))
    return result


def run_quant_models(X, y, config: QuantConfig, predict_rows: int = 1) -> dict[str, Any]:
    """Train configured models on one shared feature matrix and return normalized outputs."""
    config = config.normalized()
    valid = X.notna().all(axis=1) & y.notna()
    X, y = X.loc[valid], y.loc[valid]
    X_train, X_test, y_train, y_test = _split(X, y, config.test_size)
    X_predict = X.tail(predict_rows)
    jobs = [(family, name) for family, names in config.model_families.items() for name in names]
    outputs: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=config.max_workers or min(len(jobs), 8)) as executor:
        futures = [executor.submit(_fit_one, family, name, X_train, y_train, X_test, y_test, X_predict, config) for family, name in jobs]
        for future in as_completed(futures):
            outputs.append(future.result())
    outputs.sort(key=lambda item: (item["family"], item["model"]))
    ensembles = [item for family in config.model_families if (item := _ensemble(outputs, family))]
    selected = _select_best(outputs)
    return {
        "config": asdict(config),
        "target_mode": config.target_mode,
        "horizon": config.horizon,
        "models": outputs,
        "ensembles": ensembles,
        "selected": selected,
        "reliable": bool(selected and selected["metrics"].get("accepted", False)),
        "reliability_message": (
            "Quant signal passed baseline reliability gate."
            if selected and selected["metrics"].get("accepted", False)
            else "Quant models did not beat the validation baseline; treat output as informational only."
        ),
    }


def _select_best(outputs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not outputs:
        return None
    accepted = [item for item in outputs if item["metrics"].get("accepted", True)]
    if not accepted:
        return None
    return max(accepted, key=lambda item: item["metrics"].get("reliability", -float("inf")))