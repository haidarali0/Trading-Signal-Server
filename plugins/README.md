# Plugin contributor guide

This project has two plugin contracts. Inference plugins produce a signal; preprocessing plugins derive extra context before inference. Each built-in plugin has a standalone guide linked below.

## Inference plugins

The built-in `model` inference plugin routes the selected model to the configured provider and supports Jev typed decisions as well as GenAI/chat models. Implement `plugins.InferencePlugin` and its `infer(request)` method to add a custom inference backend. Return `(signal_dict, usage)`. The shared validator requires:

- `scenario`: `up`, `down`, or `no_trade`
- numeric `confidence` from 0 to 1
- positive numeric `entry_price`
- numeric `target_price` and `stop_loss`
- positive numeric `expected_time`
- string `analysis`

Select the built-in plugin with `--inference-plugin model`, or a custom implementation with `--inference-plugin package.module:ClassName`. The plugin receives an `InferenceRequest` containing market JSON, symbol, timeframe, optional web context/model/prompt, and skill name. Prompt skills are applied by the built-in model plugin.

The built-in inference catalog contains only `model`. See the [model inference
plugin guide](docs/inference/model/README.md).


## Preprocessing plugins

Implement `plugins.PreprocessingPlugin.transform(market_data)`. Return a JSON-serializable dictionary of derived features. Do not replace source market data; the runner stores non-empty results under `derived_features` using the selected plugin name. Preprocessors run in order, and later preprocessors receive earlier derived features.

Select built-ins with `--preprocessors none`, `fibonacci`, or `price_change`, or use an installed implementation with `--preprocessors package.module:ClassName`.

- [No-op preprocessor](docs/preprocessors/none/README.md)
- [Fibonacci preprocessor](docs/preprocessors/fibonacci/README.md)
- [Price-change preprocessor](docs/preprocessors/price_change/README.md)

Backtests provide only data available at the historical evaluation point. Custom preprocessors should likewise avoid introducing future data or making hidden network calls.
