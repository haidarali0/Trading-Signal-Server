# Skill contributor guide

A skill is supplemental instruction/knowledge text for the `model` inference plugin. It is appended to the existing base prompt (or selected custom prompt); it must not replace the prompt's required signal format.

Skills apply to Jev and GenAI/chat models when using the built-in `model`
inference plugin.

## Add a skill

1. Create a folder named for the skill under `skills/`.
2. Add `instructions.txt` containing only the additional guidance.
3. Add a `README.md` describing its purpose, intended use, and limitations.
4. Select it with `--inference-skill <folder-name>`.

Example:

```text
skills/
  risk-aware/
    README.md
    instructions.txt
```

Use plain text in `instructions.txt`. Keep guidance focused and compatible with the base output contract. Skills are prompt text, not executable code or preprocessing plugins.

The built-in `default` skill provides shared conservative market-analysis
guidance. Legacy root-level `skills/<name>.txt` files remain supported; new
contributions should use the folder layout so each skill has its own
documentation.

- [Default skill](default/README.md)
- [Risk-first signal evaluation](risk_first/README.md)
- [Market structure and confirmation](market_structure/README.md)
