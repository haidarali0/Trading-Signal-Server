"""Compatibility import for the default chat prompt stored in ``prompts/``."""

from pathlib import Path

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "genai_default_trading.txt"
)
prompt = DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")
