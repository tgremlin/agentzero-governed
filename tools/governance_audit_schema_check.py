#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from python.governance_runtime.audit_events import SCHEMA_VERSION, TAXONOMY_VERSION
from python.helpers.governance_gate import load_governance_events


def evaluate_event_schema_health(
    events: list[dict[str, Any]],
    *,
    require_events: bool,
    expected_schema_version: str = SCHEMA_VERSION,
    expected_taxonomy_version: str = TAXONOMY_VERSION,
) -> dict[str, Any]:
    required_fields = ("event_id", "event_type", "run_id", "actor_id", "actor_type")
    missing_required = 0
    schema_mismatch = 0
    taxonomy_mismatch = 0

    for event in events:
        if not isinstance(event, dict):
            missing_required += 1
            continue
        if any(not str(event.get(field, "")).strip() for field in required_fields):
            missing_required += 1
        if str(event.get("schema_version", "")).strip() != expected_schema_version:
            schema_mismatch += 1
        if str(event.get("taxonomy_version", "")).strip() != expected_taxonomy_version:
            taxonomy_mismatch += 1

    checks = [
        {
            "name": "events_present",
            "ok": (len(events) > 0) if require_events else True,
            "details": {"count": len(events), "require_events": bool(require_events)},
        },
        {
            "name": "required_fields",
            "ok": missing_required == 0,
            "details": {"missing_required_count": missing_required},
        },
        {
            "name": "schema_version",
            "ok": schema_mismatch == 0,
            "details": {
                "expected": expected_schema_version,
                "mismatch_count": schema_mismatch,
            },
        },
        {
            "name": "taxonomy_version",
            "ok": taxonomy_mismatch == 0,
            "details": {
                "expected": expected_taxonomy_version,
                "mismatch_count": taxonomy_mismatch,
            },
        },
    ]

    return {
        "ok": all(bool(item.get("ok")) for item in checks),
        "event_count": len(events),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate governed audit events against frozen schema/taxonomy versions."
    )
    parser.add_argument("--project-name", default="", help="Optional project filter.")
    parser.add_argument("--limit", type=int, default=500, help="Max events to inspect.")
    parser.add_argument("--require-events", action="store_true", help="Fail if no events are present.")
    parser.add_argument("--output", default="", help="Optional output path for JSON report.")
    args = parser.parse_args()

    events = load_governance_events(
        project_name=str(args.project_name or "").strip() or None,
        limit=max(1, int(args.limit)),
    )
    report = evaluate_event_schema_health(events, require_events=bool(args.require_events))

    output = str(args.output or "").strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, sort_keys=True))
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
