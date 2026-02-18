from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from python.helpers.governance_training_lifecycle import load_training_lifecycle_events


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(raw)
    except Exception:
        return None


def _trace_root() -> Path:
    env = str(os.environ.get("A0_GOV_TRACE_DIR", "")).strip()
    if env:
        return Path(env)
    return Path("/a0/usr/governance/datasets")


def _dataset_exports(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/*.manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        out.append(
            {
                "kind": "dataset_exports",
                "id": str(path),
                "generated_at": payload.get("generated_at"),
                "project_name": payload.get("project_name"),
                "purpose": payload.get("purpose"),
                "record_count": int(payload.get("record_count", 0) or 0),
                "gold_count": int(payload.get("gold_count", 0) or 0),
                "source_event_count": int(payload.get("source_event_count", 0) or 0),
                "sha256": payload.get("sha256"),
            }
        )
    return out


def _training_decisions(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/*.json")):
        name = path.name.lower()
        if "trigger" not in name and "release-gate" not in name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        generated_at = str(payload.get("generated_at", "")).strip() or None
        decision = payload.get("decision")
        if decision is None and "trigger_training" in payload:
            decision = "trigger" if bool(payload.get("trigger_training")) else "hold"
        out.append(
            {
                "kind": "training_decisions",
                "id": str(path),
                "generated_at": generated_at,
                "decision": decision,
                "eligible_manifests": payload.get("eligible_manifests"),
                "total_records": payload.get("total_records"),
                "total_gold": payload.get("total_gold"),
            }
        )
    return out


def _training_lifecycle() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in load_training_lifecycle_events(limit=500):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "kind": "training_lifecycle",
                "id": str(item.get("event_ts", "")),
                "generated_at": item.get("event_ts"),
                "event_type": item.get("event_type"),
                "stage": item.get("stage"),
                "status": item.get("status"),
                "project_name": item.get("project_name"),
                "run_id": item.get("run_id"),
                "details": item.get("details"),
            }
        )
    return out


def load_system_trace_items(*, type_filter: str = "") -> list[dict[str, Any]]:
    root = _trace_root()
    dataset_items = _dataset_exports(root)
    training_items = _training_decisions(root)
    lifecycle_items = _training_lifecycle()
    all_items = dataset_items + training_items + lifecycle_items

    def _item_ts(item: dict[str, Any]) -> dt.datetime:
        parsed = _parse_iso(item.get("generated_at"))
        if parsed is not None:
            return parsed
        try:
            return dt.datetime.fromtimestamp(Path(str(item.get("id", ""))).stat().st_mtime, tz=dt.timezone.utc)
        except Exception:
            return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)

    all_items.sort(key=_item_ts, reverse=True)
    wanted = str(type_filter).strip().lower()
    if not wanted:
        return all_items
    return [item for item in all_items if str(item.get("kind", "")).strip().lower() == wanted]
