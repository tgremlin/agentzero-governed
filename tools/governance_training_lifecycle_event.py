#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from python.helpers.governance_training_lifecycle import append_training_lifecycle_event


def main() -> int:
    parser = argparse.ArgumentParser(description="Append governed training lifecycle event.")
    parser.add_argument(
        "--stage",
        required=True,
        choices=["trigger", "eval", "promotion", "rollback"],
        help="Lifecycle stage.",
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=["started", "succeeded", "failed", "skipped"],
        help="Lifecycle status.",
    )
    parser.add_argument("--project-name", default="", help="Optional project name.")
    parser.add_argument("--run-id", default="", help="Optional governed run id.")
    parser.add_argument("--details", default="{}", help="Optional JSON object with extra fields.")
    args = parser.parse_args()

    details_raw = str(args.details).strip() or "{}"
    try:
        details = json.loads(details_raw)
    except Exception:
        details = {}
    if not isinstance(details, dict):
        details = {}

    payload = {
        "event_type": "training.lifecycle",
        "stage": str(args.stage),
        "status": str(args.status),
        "project_name": str(args.project_name).strip() or None,
        "run_id": str(args.run_id).strip() or None,
        "details": details,
    }
    saved = append_training_lifecycle_event(payload)
    print(json.dumps({"ok": True, "event": saved}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
