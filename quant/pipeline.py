"""Pipeline helpers for loading project candle data and transforming it for models."""

from __future__ import annotations

from typing import Sequence

from .data import load_candle_dataset, load_feature_frame
from .processing import transform_dataset
from .targets import build_target


# Function: prepare_quant_dataset
def prepare_quant_dataset(
    interval: str | None = None,
    limit: int | None = None,
    target_column: str = "close",
    include_ohlcv: bool = True,
    include_indicators: bool = True,
    indicators_list: Sequence[str] | None = None,
    shift: int = 1,
    transform_mode: str = "none",
    n_bins: int | None = None,
    columns: Sequence[str] | None = None,
    target_mode: str = "raw_price",
    direction_threshold: float = 0.001,
):
    """Load candles and indicators from the project getter and return transformed X/y."""
    if target_mode == "raw_price" and target_column != "close":
        X, y = load_candle_dataset(
            interval=interval, limit=limit, target_column=target_column,
            include_ohlcv=include_ohlcv, include_indicators=include_indicators,
            indicators_list=indicators_list, shift=shift,
        )
    else:
        feature_frame = load_feature_frame(
            interval=interval, limit=limit, include_ohlcv=include_ohlcv,
            include_indicators=include_indicators, indicators_list=indicators_list,
        )
        candles = feature_frame[["open", "high", "low", "close", "volume"]]
        y = build_target(candles, mode=target_mode, horizon=shift, direction_threshold=direction_threshold)
        X = feature_frame.drop(columns=["close"], errors="ignore")
        valid = y.notna()
        X, y = X.loc[valid], y.loc[valid]
    X_transformed = transform_dataset(
        X,
        mode=transform_mode,
        n_bins=n_bins if n_bins is not None else 10,
        columns=columns,
    )
    return X_transformed, y


# Function: available_transform_modes
def available_transform_modes() -> list[str]:
    """Return supported output transformation modes."""
    return ["none", "bins", "average", "log"]
