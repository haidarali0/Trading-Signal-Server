"""Prompt skills selectable by the LLM inference plugin."""

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent


def available_skills() -> list[str]:
    """Return built-in and installed prompt skill names."""
    names = {"default"}
    names.update(path.stem for path in SKILLS_DIR.glob("*.txt") if path.is_file())
    names.update(
        path.name
        for path in SKILLS_DIR.iterdir()
        if path.is_dir() and (path / "instructions.txt").is_file()
    )
    return sorted(names)


def load_skill_instructions(name: str) -> str:
    """Load additive instructions; skills never replace the base prompt."""
    skill_name = str(name or "").strip()
    if skill_name not in available_skills():
        raise ValueError(f"Unknown inference skill '{skill_name}'. Available: {', '.join(available_skills())}")
    path = SKILLS_DIR / skill_name / "instructions.txt"
    if not path.is_file():
        path = SKILLS_DIR / f"{skill_name}.txt"
    return path.read_text(encoding="utf-8")
