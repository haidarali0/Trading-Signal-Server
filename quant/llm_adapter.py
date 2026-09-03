"""Helpers to convert regression output into LLM-ready context."""

from __future__ import annotations

from typing import Any


# Function: predictions_to_llm_context
def predictions_to_llm_context(
    predictions,
    feature_names: list[str] | None = None,
    additional_info: dict[str, Any] | None = None,
) -> str:
    """Format prediction results as a structured text block for LLM input."""
    lines: list[str] = ["Regression model predictions:"]
    if feature_names is not None:
        lines.append(f"Features: {', '.join(feature_names)}")
    for i, value in enumerate(predictions, start=1):
        lines.append(f"- Prediction {i}: {value:.6f}")

    if additional_info:
        lines.append("Additional info:")
        for key, val in additional_info.items():
            lines.append(f"- {key}: {val}")

    lines.append(
        "Use these predictions as an input signal to the LLM analysis pipeline."
    )
    return "\n".join(lines)


# Function: features_to_llm_context
def features_to_llm_context(
    features,
    label: str | None = None,
    max_rows: int = 5,
) -> str:
    """Format a feature matrix into a short LLM-ready context string."""
    if hasattr(features, "to_dict"):
        data = features.head(max_rows).to_dict(orient="records")
    else:
        data = list(features)

    header = ["Regression feature matrix summary:"]
    if label is not None:
        header.append(f"Label: {label}")
    if hasattr(features, "columns"):
        header.append(f"Columns: {', '.join(str(c) for c in features.columns)}")

    lines = header + [f"Row {i + 1}: {record}" for i, record in enumerate(data)]
    lines.append("Use this feature summary as input context for LLM analysis.")
    return "\n".join(lines)


# Function: explain_quant_output
def explain_quant_output(
    model_name: str,
    predictions,
    feature_rows,
    target: str,
    shift: int = 1,
    transform: str = "none",
    input_set: str | None = None,
    max_rows: int = 1,
) -> dict[str, Any]:
    """Build a simple unified quant output payload for the LLM."""
    if hasattr(feature_rows, "head"):
        feature_records = feature_rows.head(max_rows).to_dict(orient="records")
    else:
        feature_records = [dict(feature_rows)]

    prediction_values = [float(v) for v in predictions]
    explanation_lines = [
        f"Model: {model_name}",
        f"Target: {target}",
        f"Shift: {shift}",
        f"Transform: {transform}",
        f"Input set: {input_set or 'both'}",
        "Predictions:",
        f"- {prediction_values}",
        "Feature example rows:",
    ]
    for i, record in enumerate(feature_records, start=1):
        explanation_lines.append(f"- Row {i}: {record}")

    return {
        "model": model_name,
        "target": target,
        "shift": shift,
        "transform": transform,
        "input_set": input_set,
        "predictions": prediction_values,
        "features": feature_records,
        "explanation": "\n".join(explanation_lines),
    }
