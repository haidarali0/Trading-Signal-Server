# Model inference plugin

The `model` inference plugin is the model-backed inference path. It sends the assembled market information, configured model, base/custom prompt, and optional web context to the provider-aware inference function.

The selected skill is loaded as supplemental instruction text and appended to the base or custom prompt. It does not replace the required signal format.

## Model compatibility

This is the only built-in inference plugin. Ordinary GenAI/chat models can use
OpenRouter chat completions. Configured Jev decision models use Jev's typed
target-choice workflow through the direct TypeSafe API when configured, or
OpenRouter's decisions endpoint otherwise. Other supported OpenRouter models
are sent through chat completions. For Jev, use the
Fibonacci preprocessor and Jev decision prompt; ordinary chat prompts and their
JSON signal contract are not used by Jev's typed-choice adapter.

## Use

```bash
python main.py --inference-plugin model --inference-skill risk_first
```

`model` is the default inference plugin. Configure the model and provider API credentials using the project's normal settings.

## Implementation

`plugins.model.ModelInferencePlugin` implements the shared `InferencePlugin` contract. The shared dispatcher validates its signal result before live or backtest code consumes it.
