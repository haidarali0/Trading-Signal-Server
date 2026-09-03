import os
import json
from pathlib import Path

import ml_builder.ml_data as ml


def backup_and_remove(path: Path):
    bak = None
    if path.exists():
        bak = path.with_suffix('.bak')
        path.replace(bak)
    return bak


def restore_backup(path: Path, bak: Path | None):
    if path.exists():
        path.unlink()
    if bak and bak.exists():
        bak.replace(path)


def test_append_list_update_export(tmp_path):
    # isolate dataset to temp file
    original_file = ml.DATA_FILE
    temp_file = tmp_path / "dataset.jsonl"
    ml.DATA_FILE = temp_file

    try:
        # ensure clean start
        if temp_file.exists():
            temp_file.unlink()

        r1 = ml.append_record({"symbol": "TEST", "predicted_label": "up"})
        r2 = ml.append_record({"symbol": "TEST", "predicted_label": "down"})

        records = ml.list_records(limit=10)
        assert isinstance(records, list)
        assert len(records) == 2

        exported = ml.export_records()
        assert len(exported) == 2

        # update record
        rec_id = r1["id"]
        updated = ml.update_record(rec_id, {"ground_truth": "up"})
        assert updated is not None
        assert updated.get("ground_truth") == "up"

    finally:
        # restore
        ml.DATA_FILE = original_file
        if temp_file.exists():
            temp_file.unlink()


def test_backtest_signal_normalizes_live_equivalent_fields(tmp_path):
    original_file = ml.DATA_FILE
    temp_file = tmp_path / "dataset.jsonl"
    ml.DATA_FILE = temp_file

    try:
        if temp_file.exists():
            temp_file.unlink()

        rec = ml.append_record({
            "mode": "backtest",
            "symbol": "BTCUSDT",
            "predicted_label": "up",
            "confidence": 0.91,
            "entry_price": 100.0,
            "target_price": 105.0,
            "stop_loss": 97.0,
            "expected_time": 12,
            "analysis": "Signal from historical test window",
            "model_name": "gpt-4o-mini",
            "features": {"symbol": "BTCUSDT", "interval": "1h"},
        })

        assert rec["analysis"] == "Signal from historical test window"
        assert rec["model_name"] == "gpt-4o-mini"
        assert rec["features"]["interval"] == "1h"

        saved = ml.list_records(limit=1)
        assert saved[0]["mode"] == "backtest"
        assert saved[0]["analysis"] == "Signal from historical test window"

    finally:
        ml.DATA_FILE = original_file
        if temp_file.exists():
            temp_file.unlink()


def test_append_record_does_not_duplicate_same_signal_window(tmp_path):
    original_file = ml.DATA_FILE
    temp_file = tmp_path / "dataset.jsonl"
    ml.DATA_FILE = temp_file

    try:
        if temp_file.exists():
            temp_file.unlink()

        base = {
            "mode": "backtest",
            "symbol": "BTCUSDT",
            "timestamp": "2024-01-01T00:00:00Z",
            "predicted_label": "up",
            "confidence": 0.9,
            "entry_price": 100.0,
            "target_price": 105.0,
            "stop_loss": 97.0,
            "expected_time": 12,
            "chart_marker": {
                "entry_time": "2024-01-01T00:00:00Z",
                "outcome_time": "2024-01-01T12:00:00Z",
                "outcome": "success",
            },
        }

        ml.append_record(base)
        ml.append_record({**base, "confidence": 0.92, "id": "duplicate-check"})
        ml.append_record({**base, "timestamp": "2024-01-01T00:05:00Z", "chart_marker": {**base["chart_marker"], "entry_time": "2024-01-01T00:05:00Z"}})

        records = ml.list_records(limit=10)
        assert len(records) == 2
        assert [r["timestamp"] for r in records] == ["2024-01-01T00:05:00Z", "2024-01-01T00:00:00Z"]

    finally:
        ml.DATA_FILE = original_file
        if temp_file.exists():
            temp_file.unlink()
