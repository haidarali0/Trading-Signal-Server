# No-op preprocessor

**Model compatibility:** Model-agnostic. It adds no derived features to Jev or
GenAI/chat workflows.

The built-in `none` preprocessor is the default. It returns no derived features, leaving the normalized market payload unchanged.

## Use

```bash
python main.py --preprocessors none
```

Use it as a baseline when comparing inference runs with feature-generating preprocessors.

## Implementation

`plugins.preprocessors.noop.NoOpPreprocessor` implements `PreprocessingPlugin.transform(market_data)` and returns an empty dictionary.
