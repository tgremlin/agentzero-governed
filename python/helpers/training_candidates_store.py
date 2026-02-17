from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


_VALID_STATUSES = {"ready", "pending_review", "exclude"}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_project_key(project_name: str | None) -> str:
    if not project_name:
        return "global"
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", str(project_name).strip())[:128] or "global"


def _resolve_base_dir() -> Path:
    from python.helpers.governance_gate import _resolve_governance_storage_dir  # lazy import to avoid cycles

    base = _resolve_governance_storage_dir() / "training_candidates"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _state_path(project_name: str | None) -> Path:
    key = _safe_project_key(project_name)
    return _resolve_base_dir() / f"{key}.json"


def load_candidate_overrides(project_name: str | None) -> dict[str, dict[str, Any]]:
    path = _state_path(project_name)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    items = payload.get("items")
    if not isinstance(items, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for cand_id, meta in items.items():
        if not isinstance(cand_id, str) or not isinstance(meta, dict):
            continue
        status = str(meta.get("training_status", "")).strip().lower()
        if status and status not in _VALID_STATUSES:
            continue
        out[cand_id] = {
            "training_status": status,
            "note": str(meta.get("note", "")),
            "updated_at": str(meta.get("updated_at", "")),
        }
    return out


def save_candidate_overrides(project_name: str | None, items: dict[str, dict[str, Any]]) -> None:
    path = _state_path(project_name)
    payload = {
        "project_name": project_name,
        "updated_at": _now_iso(),
        "items": items,
    }
    path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")


def apply_candidate_overrides(project_name: str | None, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overrides = load_candidate_overrides(project_name)
    if not overrides:
        return candidates

    for candidate in candidates:
        cid = str(candidate.get("candidate_id", "")).strip()
        if not cid or cid not in overrides:
            continue
        meta = overrides[cid]
        status = str(meta.get("training_status", "")).strip().lower()
        if status in _VALID_STATUSES:
            candidate["training_status"] = status
        note = str(meta.get("note", "")).strip()
        if note:
            candidate["note"] = note
        updated_at = str(meta.get("updated_at", "")).strip()
        if updated_at:
            candidate["updated_at"] = updated_at
    return candidates


def bulk_update_candidates(
    project_name: str | None,
    candidate_ids: list[str],
    *,
    training_status: str | None = None,
    note: str = "",
    reset: bool = False,
) -> dict[str, Any]:
    ids = [str(x).strip() for x in candidate_ids if str(x).strip()]
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"updated": 0, "candidate_ids": []}

    overrides = load_candidate_overrides(project_name)

    if reset:
        updated = 0
        for cid in ids:
            if cid in overrides:
                overrides.pop(cid, None)
                updated += 1
        save_candidate_overrides(project_name, overrides)
        return {"updated": updated, "candidate_ids": ids, "action": "reset"}

    status = str(training_status or "").strip().lower()
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid training_status: {training_status}")

    for cid in ids:
        overrides[cid] = {
            "training_status": status,
            "note": str(note or ""),
            "updated_at": _now_iso(),
        }
    save_candidate_overrides(project_name, overrides)
    return {"updated": len(ids), "candidate_ids": ids, "training_status": status}
