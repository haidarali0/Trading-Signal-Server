"""Feature processing utilities for quant datasets."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


# Function: bin_dataframe
def bin_dataframe(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    n_bins: int = 10,
    labels: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Convert numeric columns to binned numerical ranges."""
    if columns is None:
        columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]

    result = df.copy()
    for column in columns:
        if column not in result.columns:
            continue
        series = result[column].astype(float).dropna()
        if series.empty:
            continue
        if labels is None:
            labels = [f"{column}_bin_{i}" for i in range(n_bins)]
        binned = pd.cut(series, bins=n_bins, labels=False, duplicates="drop")
        result[column] = binned.astype(float)
    return result


# Function: rolling_average
def rolling_average(
    df: pd.DataFrame,
    window: int = 3,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Replace numeric columns with a rolling average over a fixed window."""
    if columns is None:
        columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]

    result = df.copy()
    for column in columns:
        if column not in result.columns:
            continue
        result[column] = result[column].astype(float).rolling(window, min_periods=1).mean()
    return result


# Function: log_transform
def log_transform(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    shift: float = 1e-9,
) -> pd.DataFrame:
    """Apply a natural log transform to numeric feature columns."""
    if columns is None:
        columns = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]

    result = df.copy()
    for column in columns:
        if column not in result.columns:
            continue
        result[column] = np.log(result[column].astype(float) + shift)
    return result


# Function: transform_dataset
def transform_dataset(
    df: pd.DataFrame,
    mode: str = "none",
    n_bins: int = 10,
    average_window: int = 3,
    log_scale: bool = False,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Apply a feature transformation mode to the dataset."""
    if mode == "bins":
        return bin_dataframe(df, columns=columns, n_bins=n_bins)
    if mode == "average":
        return rolling_average(df, window=average_window, columns=columns)
    if mode == "log":
        return log_transform(df, columns=columns)
    if log_scale:
        return log_transform(df, columns=columns)
    return df.copy()
