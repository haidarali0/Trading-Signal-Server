"""Target builders shared by all quantitative model families."""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET_MODES = (
    "raw_price",
    "percentage_return",
    "log_return",
    "binary_direction",
    "ternary_direction",
    "future_volatility",
)


def available_target_modes() -> list[str]:
    return list(TARGET_MODES)


def build_target(
    candles: pd.DataFrame,
    mode: str = "raw_price",
    horizon: int = 1,
    direction_threshold: float = 0.001,
) -> pd.Series:
    """Build a forward-looking target without filling unavailable future rows."""
    if mode not in TARGET_MODES:
        raise ValueError(f"Unsupported target mode '{mode}'. Available: {', '.join(TARGET_MODES)}")
    if horizon < 1:
        raise ValueError("Target horizon must be at least 1.")
    close = candles["close"].astype(float)
    future_return = close.shift(-horizon).div(close).sub(1.0)

    if mode == "raw_price":
        return close.shift(-horizon).rename("target")
    if mode == "percentage_return":
        return future_return.rename("target")
    if mode == "log_return":
        return np.log1p(future_return).rename("target")
    if mode == "binary_direction":
        return future_return.gt(direction_threshold).astype("float").where(future_return.notna()).rename("target")
    if mode == "ternary_direction":
        return pd.Series(
            np.select(
                [future_return > direction_threshold, future_return < -direction_threshold],
                [1.0, -1.0],
                default=0.0,
            ),
            index=candles.index,
            name="target",
        ).where(future_return.notna())

    log_returns = np.log(close).diff()
    volatility_window = max(2, horizon)
    future_returns = pd.concat(
        [log_returns.shift(-step) for step in range(1, volatility_window + 1)],
        axis=1,
    )
    target = future_returns.std(axis=1, ddof=1)
    return target.where(future_returns.notna().all(axis=1)).rename("target")
