# Fibonacci preprocessor

**Model compatibility:** Model-agnostic feature output. It is the required
built-in feature source for the configured Jev Fibonacci target-selection
workflow; chat/GenAI prompts can also use its levels when included in input.

The `fibonacci` preprocessor derives retracement levels from the highest high and lowest low in the supplied `price_history`. It adds the levels for ratios 0, 0.236, 0.382, 0.5, 0.618, 0.786, and 1, plus the nearest level when a current price is available.

Its output is added at `derived_features.fibonacci`; original candles and other market fields are preserved. If the candle window has no usable high/low range, the result reports `status: unavailable` and a reason.

## Use

```bash
python main.py --preprocessors fibonacci
```

## Limitations

The swing high and low are selected from the full supplied candle window without trend or pivot detection. Levels are descriptive features, not guarantees of support, resistance, or future price movement. In backtests, only candles available at that test point are supplied.

## Implementation

`plugins.preprocessors.fibonacci.FibonacciPreprocessor` implements `PreprocessingPlugin.transform(market_data)`.
