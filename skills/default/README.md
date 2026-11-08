# Default skill

**Model compatibility:** Applies to Jev and GenAI/chat models through the
`model` inference plugin.

`default` provides general, conservative guidance for this project's market
analysis: consider all supplied context, avoid inventing missing facts, account
for uncertainty, and follow the selected prompt's output contract. It is the
general-purpose skill used unless another skill is selected.

## Use

```bash
python main.py --inference-skill default
```

This skill supplements the selected prompt; it does not replace or override its
required response format.
