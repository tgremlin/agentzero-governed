#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from python.helpers.governance_training_dashboard import build_training_dashboard_snapshot
from python.helpers.system_trace_store import load_system_trace_items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic governed training-ops dashboard snapshot from system trace artifacts."
    )
    parser.add_argument("--project-name", default="", help="Optional project filter.")
    parser.add_argument("--output", default="", help="Optional output path for JSON snapshot.")
    args = parser.parse_args()

    snapshot = build_training_dashboard_snapshot(
        load_system_trace_items(),
        project_name=str(args.project_name or "").strip(),
    )

    output = str(args.output or "").strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(snapshot, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
