import pandas as pd

from engine.plot import build_projection_index, build_projection_series


def test_build_projection_index_and_series_handle_short_history():
    history = pd.to_datetime(["2024-01-01 00:00:00", "2024-01-02 00:00:00"])

    future_index = build_projection_index(history, 6)
    assert len(future_index) == 6
    assert future_index[-1] > history[-1]

    series = build_projection_series(pd.DatetimeIndex(history.tolist() + future_index.tolist()), price=42.0, total_rows=len(history) + len(future_index), projection_steps=6)
    assert series.iloc[-1] == 42.0
    assert series.iloc[-2] == 42.0
    assert series.notna().sum() == 6
