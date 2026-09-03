"""Data preparation helpers for quantitative models."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from crypto_data.getter import get_candles
from crypto_data.indicators import calculate_indicators


def _feature_frame_from_candles(
    candles: pd.DataFrame,
    include_ohlcv: bool = True,
    include_indicators: bool = True,
    indicators_list: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load the common feature matrix used by every target and model family."""
    feature_parts = []
    if include_ohlcv:
        feature_parts.append(candles[["open", "high", "low", "close", "volume"]])
    else:
        feature_parts.append(candles[["close"]])
    if include_indicators:
        feature_parts.append(calculate_indicators(candles, indicators_list=indicators_list))
    return pd.concat(feature_parts, axis=1) if feature_parts else pd.DataFrame(index=candles.index)


def load_feature_frame(
    interval: str | None = None,
    limit: int | None = None,
    include_ohlcv: bool = True,
    include_indicators: bool = True,
    indicators_list: Sequence[str] | None = None,
) -> pd.DataFrame:
    candles = get_candles(interval=interval, limit=limit)
    return _feature_frame_from_candles(candles, include_ohlcv, include_indicators, indicators_list)


# Function: create_dataset
def create_dataset(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: Sequence[str] | None = None,
    dropna: bool = True,
):
    """Split a DataFrame into feature matrix and target vector."""
    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' not found in DataFrame.")

    if feature_columns is None:
        feature_columns = [column for column in df.columns if column != target_column]

    if isinstance(feature_columns, str):
        feature_columns = [feature_columns]

    if dropna:
        df = df.dropna(subset=list(feature_columns) + [target_column])

    X = df.loc[:, feature_columns].copy()
    y = df.loc[:, target_column].copy()
    return X, y, list(feature_columns)


# Function: dataframe_to_features
def dataframe_to_features(df: pd.DataFrame, feature_columns: Sequence[str]) -> pd.DataFrame:
    """Extract a feature matrix from a DataFrame."""
    missing = [col for col in feature_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")
    return df.loc[:, feature_columns].copy()


# Function: load_candle_dataset
def load_candle_dataset(
    interval: str | None = None,
    limit: int | None = None,
    target_column: str = "close",
    include_ohlcv: bool = True,
    include_indicators: bool = True,
    indicators_list: Sequence[str] | None = None,
    shift: int = 1,
    dropna: bool = False,
):
    """Load historical candle and indicator data from project getter and return features and target."""
    candles = get_candles(interval=interval, limit=limit)
    full_feature_df = _feature_frame_from_candles(
        candles, include_ohlcv, include_indicators, indicators_list
    )

    if target_column not in full_feature_df.columns:
        raise ValueError(f"Target column '{target_column}' is not available in the dataset.")

    ohlcv_columns = ["open", "high", "low", "close", "volume"]
    indicator_columns = [column for column in full_feature_df.columns if column not in ohlcv_columns]
    selected_feature_columns = []
    if include_ohlcv:
        selected_feature_columns.extend(ohlcv_columns)
    if include_indicators:
        selected_feature_columns.extend(indicator_columns)

    selected_feature_columns = [column for column in selected_feature_columns if column != target_column]
    feature_df = full_feature_df.loc[:, selected_feature_columns].copy() if selected_feature_columns else pd.DataFrame(index=candles.index)

    target = full_feature_df[target_column].shift(-shift)
    if dropna:
        valid_index = target.dropna().index
        feature_df = feature_df.loc[valid_index].copy()
        target = target.loc[valid_index].copy()
    return feature_df, target
