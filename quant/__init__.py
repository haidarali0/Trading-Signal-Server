"""Quantitative regression utilities for model training and LLM integration."""

from .data import (
    create_dataset,
    dataframe_to_features,
    load_feature_frame,
    load_candle_dataset,
)
from .llm_adapter import explain_quant_output, features_to_llm_context, predictions_to_llm_context
from .model_zoo import MODEL_REGISTRY, available_models, get_model
from .model_zoo import available_classifiers, get_classifier
from .processing import transform_dataset
from .pipeline import available_transform_modes, prepare_quant_dataset
from .targets import available_target_modes, build_target
from .ensemble import QuantConfig, run_quant_models
from .trainer import (
    evaluate_regression,
    predict_with_model,
    train_regressor,
    train_regressor_and_report,
)

__all__ = [
    "available_transform_modes",
    "create_dataset",
    "dataframe_to_features",
    "features_to_llm_context",
    "explain_quant_output",
    "load_candle_dataset",
    "load_feature_frame",
    "predictions_to_llm_context",
    "prepare_quant_dataset",
    "MODEL_REGISTRY",
    "available_models",
    "get_model",
    "available_classifiers",
    "get_classifier",
    "transform_dataset",
    "train_regressor",
    "train_regressor_and_report",
    "predict_with_model",
    "evaluate_regression",
    "available_target_modes",
    "build_target",
    "QuantConfig",
    "run_quant_models",
]
