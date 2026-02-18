from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from typing import Any

from python.helpers.governance_dataset_quality import score_episode

DATASET_VERSION = "governance.flywheel.v1"
CONSENT_ORDER = {"audit_only": 0, "eval_allowed": 1, "training_allowed": 2}


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


def _event_ts(event: dict[str, Any]) -> dt.datetime:
    for key in ("event_ts", "created_at", "updated_at"):
        parsed = _parse_iso(event.get(key))
        if parsed is not None:
            return parsed
    return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)


def _normalize_consent(value: Any) -> str:
    consent = str(value or "").strip().lower()
    if consent in CONSENT_ORDER:
        return consent
    return "eval_allowed"


def _episode_id(run_id: str, events: list[dict[str, Any]]) -> str:
    material = json.dumps(
        {
            "run_id": run_id,
            "count": len(events),
            "types": [str(e.get("type", "")) for e in events],
        },
        sort_keys=True,
        default=str,
    )
    return "ep_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _consent_for_events(events: list[dict[str, Any]]) -> str:
    best = "audit_only"
    for event in events:
        consent = _normalize_consent(event.get("consent_scope"))
        if CONSENT_ORDER[consent] > CONSENT_ORDER[best]:
            best = consent
    return best


def _is_allowed(consent: str, purpose: str) -> bool:
    if purpose == "training":
        return consent == "training_allowed"
    return consent in {"eval_allowed", "training_allowed"}


def build_episode_records(
    events: list[dict[str, Any]],
    *,
    purpose: str = "eval",
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if not isinstance(event, dict):
            continue
        run_id = str(event.get("run_id") or "").strip()
        if not run_id:
            continue
        grouped[run_id].append(dict(event))

    records: list[dict[str, Any]] = []
    for run_id, run_events in grouped.items():
        run_events.sort(key=_event_ts)
        consent_scope = _consent_for_events(run_events)
        if not _is_allowed(consent_scope, purpose):
            continue

        project_name = str(run_events[-1].get("project_name", "")).strip() or None
        outcome = next(
            (
                str(event.get("outcome", "")).strip().lower()
                for event in reversed(run_events)
                if str(event.get("type", "")).strip().lower() == "run.outcome"
            ),
            "",
        )
        quality = score_episode(run_events)

        records.append(
            {
                "dataset_version": DATASET_VERSION,
                "episode_id": _episode_id(run_id, run_events),
                "run_id": run_id,
                "project_name": project_name,
                "consent_scope": consent_scope,
                "purpose": purpose,
                "labels": {
                    "outcome": outcome or "unknown",
                    "event_count": len(run_events),
                    "quality_score": quality["quality_score"],
                    "train_eligible": quality["train_eligible"],
                    "gold": quality["gold"],
                    "tier": quality["tier"],
                },
                "quality": quality,
                "events": run_events,
            }
        )

    records.sort(key=lambda item: (str(item.get("project_name") or ""), str(item.get("run_id") or "")))
    return records


def episode_records_to_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, sort_keys=True, default=str) + "\n" for record in records)
