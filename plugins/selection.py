"""Formatting helpers for reporting configured extensions."""

from collections.abc import Sequence

from config import DECISION_MODELS, MODEL_NAME


def format_extension_selection(
    inference_plugin: str,
    inference_skill: str,
    preprocessors: str | Sequence[str] | None = None,
    prompt_files: str | Sequence[str] | None = None,
    model_names: Sequence[str] | None = None,
    direct_typesafe_available: bool = False,
) -> str:
    """Return a readable summary of selected inference extensions and routing."""
    if isinstance(preprocessors, str):
        selected_preprocessors = preprocessors.replace(",", " ").split()
    else:
        selected_preprocessors = [
            str(name).strip() for name in preprocessors or [] if str(name).strip()
        ]
    if not selected_preprocessors:
        selected_preprocessors = ["none"]

    if isinstance(prompt_files, str):
        selected_prompts = prompt_files.replace(",", " ").split()
    else:
        selected_prompts = [
            str(path).strip() for path in prompt_files or [] if str(path).strip()
        ]
    prompt_label = ", ".join(selected_prompts) if selected_prompts else "default"

    plugin_name = str(inference_plugin).strip()
    if plugin_name != "model":
        provider_label = "not applicable (plugin-managed)"
    else:
        selected_models = [str(name).strip().casefold() for name in model_names or []]
        if not selected_models:
            selected_models = [MODEL_NAME.casefold()]
        decision_models = {name.casefold() for name in DECISION_MODELS}
        has_jev = any(name in decision_models for name in selected_models)
        has_other_models = any(name not in decision_models for name in selected_models)
        if has_jev and direct_typesafe_available:
            provider_label = (
                "TypeSafe direct for Jev; OpenRouter for other models"
                if has_other_models
                else "TypeSafe direct API"
            )
        else:
            provider_label = "OpenRouter"

    return (
        f"[extensions] Inference plugin: {plugin_name} | "
        f"Inference skill: {inference_skill} | "
        f"Preprocessors: {', '.join(selected_preprocessors)} | "
        f"Prompt: {prompt_label} | Provider: {provider_label}"
    )


def decision_model_setup_warning(
    inference_plugin: str,
    model_names: Sequence[str] | None,
    preprocessors: Sequence[str] | None,
    prompt_files: Sequence[str] | None = None,
) -> str | None:
    """Describe missing built-in setup for the configured Jev workflow."""
    if str(inference_plugin).strip() != "model":
        return None

    selected_models = {str(name).strip().lower() for name in model_names or []}
    decision_models = {name.lower() for name in DECISION_MODELS}
    selected_preprocessors = {str(name).strip().lower() for name in preprocessors or []}
    if not selected_models.intersection(decision_models):
        return None

    selected_prompts = {
        str(path).strip().replace("\\", "/").lower().lstrip("./")
        for path in prompt_files or []
    }
    uses_jev_prompt = any(
        path == "prompts/fibonacci_decision.txt"
        or path.endswith("/prompts/fibonacci_decision.txt")
        for path in selected_prompts
    )
    setup_notes = []
    if "fibonacci" not in selected_preprocessors:
        setup_notes.append(
            "Jev's current target workflow expects Fibonacci levels; add "
            "--preprocessors fibonacci or a custom preprocessor supplying "
            "derived_features.fibonacci."
        )
    if not uses_jev_prompt:
        setup_notes.append(
            "The default chat prompt is not suitable for Jev; use "
            "--prompt-files prompts/fibonacci_decision.txt or a compatible custom Jev prompt."
        )
    if not setup_notes:
        return None

    return "[setup] " + " ".join(setup_notes)
