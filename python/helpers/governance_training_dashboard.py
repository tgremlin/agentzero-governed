from __future__ import annotations

import datetime as dt
from typing import Any


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _parse_iso(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def build_training_dashboard_snapshot(
    items: list[dict[str, Any]],
    *,
    project_name: str = "",
) -> dict[str, Any]:
    wanted_project = str(project_name).strip()
    dataset_items: list[dict[str, Any]] = []
    decision_items: list[dict[str, Any]] = []
    lifecycle_items: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        item_project = str(item.get("project_name", "")).strip()
        if wanted_project and item_project and item_project != wanted_project:
            continue

        if kind == "dataset_exports":
            dataset_items.append(item)
        elif kind == "training_decisions":
            decision_items.append(item)
        elif kind == "training_lifecycle":
            lifecycle_items.append(item)

    total_records = sum(_to_int(item.get("record_count")) for item in dataset_items)
    total_gold = sum(_to_int(item.get("gold_count")) for item in dataset_items)
    yield_ratio = (float(total_gold) / float(total_records)) if total_records > 0 else 0.0

    latest_dataset = max(
        (_parse_iso(item.get("generated_at")) for item in dataset_items),
        default=None,
    )
    latest_decision = max(
        (_parse_iso(item.get("generated_at")) for item in decision_items),
        default=None,
    )
    latest_lifecycle = max(
        (_parse_iso(item.get("generated_at")) for item in lifecycle_items),
        default=None,
    )

    decisions_by_type: dict[str, int] = {}
    for item in decision_items:
        decision = str(item.get("decision", "unknown")).strip().lower() or "unknown"
        decisions_by_type[decision] = decisions_by_type.get(decision, 0) + 1

    stage_status_counts: dict[str, dict[str, int]] = {}
    active_run_ids: set[str] = set()
    terminal_status = {"success", "succeeded", "completed", "failed", "error", "rollback", "canceled", "cancelled"}
    for item in lifecycle_items:
        stage = str(item.get("stage", "unknown")).strip().lower() or "unknown"
        status = str(item.get("status", "unknown")).strip().lower() or "unknown"
        stage_map = stage_status_counts.setdefault(stage, {})
        stage_map[status] = stage_map.get(status, 0) + 1
        run_id = str(item.get("run_id", "")).strip()
        if run_id and status not in terminal_status:
            active_run_ids.add(run_id)

    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "generated_at": now,
        "project_name": wanted_project or None,
        "sources": {
            "dataset_exports": len(dataset_items),
            "training_decisions": len(decision_items),
            "training_lifecycle": len(lifecycle_items),
        },
        "dataset_summary": {
            "total_records": total_records,
            "total_gold": total_gold,
            "gold_yield": round(yield_ratio, 6),
            "latest_generated_at": latest_dataset.isoformat().replace("+00:00", "Z") if latest_dataset else None,
        },
        "decision_summary": {
            "by_decision": decisions_by_type,
            "latest_generated_at": latest_decision.isoformat().replace("+00:00", "Z") if latest_decision else None,
        },
        "lifecycle_summary": {
            "stage_status_counts": stage_status_counts,
            "active_run_count": len(active_run_ids),
            "latest_generated_at": latest_lifecycle.isoformat().replace("+00:00", "Z") if latest_lifecycle else None,
        },
    }
