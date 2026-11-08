# Risk-first signal evaluation

**Model compatibility:** Applies through the `model` inference plugin to both
Jev typed decisions and GenAI/chat models.

This skill asks the LLM inference plugin to prefer capital preservation over
forcing a trade. It emphasizes target-versus-stop plausibility, clear invalidation,
and abstention when the supplied evidence does not justify a directional signal.

Use it with `--inference-skill risk_first`. It supplements, and never replaces,
the selected signal prompt or its output contract. It does not calculate position
size or guarantee that a trade is safe or profitable.
