# Price-change preprocessor

**Model compatibility:** Model-agnostic feature output. GenAI/chat models can
consider these levels when choosing a target. The current Jev typed-choice
adapter does not use these levels as choice options; it currently builds its
target choices from Fibonacci features.

The `price_change` preprocessor creates target prices relative to the current
price: unchanged (`0%`) and `+20%`, `+40%`, `+60%`, `+80%`, `+100%`, and their
negative counterparts. Each level includes its percentage change, calculated
price, direction, and a `usable` flag. The `-100%` level is zero and marked
unusable; models should not select it as a valid asset-price target.

Levels are added at `derived_features.price_change`. The current market price is
the anchor; when it is absent, the latest candle close is used.

## Use

```bash
python main.py --preprocessors price_change
python main.py --preprocessors fibonacci price_change
```

These are fixed percentage scenarios, not forecasts or support/resistance
levels. A large percentage move may be implausible for the selected timeframe;
evaluate it against the supplied market context rather than assuming it will be
reached.

## Implementation

`plugins.preprocessors.price_change.PriceChangePreprocessor` implements
`PreprocessingPlugin.transform(market_data)`.
