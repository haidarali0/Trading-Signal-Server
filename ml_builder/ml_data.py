"""Simple ML dataset storage helpers (JSONL) for capturing signal records.

This file was moved from the project root into the `ml_builder` package.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "ml_data"
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "dataset.jsonl"
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_identity(record: Dict[str, Any]) -> tuple[Any, ...]:
    marker = record.get('chart_marker') if isinstance(record.get('chart_marker'), dict) else {}
    features = record.get('features') if isinstance(record.get('features'), dict) else {}
    signal_time = (
        record.get('timestamp')
        or record.get('created_at')
        or record.get('time')
        or marker.get('entry_time')
        or marker.get('time')
        or features.get('timestamp')
        or features.get('time')
        or features.get('entry_time')
        or ''
    )
    predicted = record.get('predicted_label')
    if predicted is None and 'scenario' in record:
        predicted = record.get('scenario')
    return (
        str(record.get('mode') or 'signal'),
        str(record.get('symbol') or '').strip(),
        str(predicted or '').strip(),
        str(signal_time).strip(),
        record.get('entry_price'),
        record.get('target_price'),
        record.get('stop_loss'),
        record.get('expected_time'),
    )


def append_record(record: Dict[str, Any]) -> Dict[str, Any]:
    rec = dict(record)
    if 'id' not in rec:
        rec['id'] = str(uuid.uuid4())
    rec.setdefault('created_at', _now_iso())

    identity = _record_identity(rec)
    with _LOCK:
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r', encoding='utf-8') as fh:
                for line in fh:
                    try:
                        existing = json.loads(line)
                    except Exception:
                        continue
                    if _record_identity(existing) == identity:
                        return existing

        try:
            line = json.dumps(rec, default=str, ensure_ascii=False)
        except Exception:
            rec = {k: (v if isinstance(v, (str, bool, int, float, list, dict, type(None))) else str(v)) for k, v in rec.items()}
            line = json.dumps(rec, ensure_ascii=False)

        with open(DATA_FILE, 'a', encoding='utf-8') as fh:
            fh.write(line + "\n")
    return rec


def list_records(limit: int = 100, reverse: bool = True) -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    with _LOCK:
        with open(DATA_FILE, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
    if reverse:
        lines = list(reversed(lines))
    results = []
    for line in lines[:limit]:
        try:
            results.append(json.loads(line))
        except Exception:
            continue
    return results


def export_records() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    with _LOCK:
        with open(DATA_FILE, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
    results = []
    for line in lines:
        try:
            results.append(json.loads(line))
        except Exception:
            continue
    return results


def update_record(record_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return None
    updated = None
    with _LOCK:
        with open(DATA_FILE, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
        out_lines = []
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:
                out_lines.append(line)
                continue
            if str(rec.get('id')) == str(record_id):
                rec.update(updates)
                rec.setdefault('updated_at', _now_iso())
                updated = rec
            out_lines.append(json.dumps(rec, ensure_ascii=False))
        with open(DATA_FILE, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(out_lines) + ('\n' if out_lines else ''))
    return updated


if __name__ == '__main__':
    print(f"ML data file: {DATA_FILE}")
