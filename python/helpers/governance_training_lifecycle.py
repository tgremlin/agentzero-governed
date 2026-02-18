from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any


def _lifecycle_path() -> Path:
    env = str(os.environ.get("A0_GOV_TRAINING_EVENTS_FILE", "")).strip()
    if env:
        return Path(env)
    return Path("/a0/usr/governance/datasets/training-lifecycle.jsonl")


def append_training_lifecycle_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    payload.setdefault("event_ts", dt.datetime.now(dt.timezone.utc).isoformat())
    payload.setdefault("event_type", "training.lifecycle")

    path = _lifecycle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return payload


def load_training_lifecycle_events(limit: int = 200) -> list[dict[str, Any]]:
    path = _lifecycle_path()
    if not path.exists():
        return []

    out: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            out.append(payload)
        if len(out) >= max(1, int(limit)):
            break
    return out
