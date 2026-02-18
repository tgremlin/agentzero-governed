#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from python.helpers.governance_dataset_builder import (
    build_dataset_manifest,
    build_episode_records,
    episode_records_to_jsonl,
)
from python.helpers.governance_gate import load_governance_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Export governed runs into canonical episode JSONL records.")
    parser.add_argument("--project-name", default="", help="Optional governance project name filter.")
    parser.add_argument("--purpose", default="eval", choices=["eval", "training"], help="Dataset export purpose.")
    parser.add_argument("--limit", type=int, default=10000, help="Max governance events to read.")
    parser.add_argument("--output", required=True, help="Output JSONL file path.")
    parser.add_argument("--manifest-output", default="", help="Optional output JSON path for dataset manifest.")
    args = parser.parse_args()

    project_name = str(args.project_name).strip() or None
    events = load_governance_events(project_name=project_name, limit=max(1, int(args.limit)))
    records = build_episode_records(events, purpose=str(args.purpose))
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(episode_records_to_jsonl(records), encoding="utf-8")
    manifest_output = str(args.manifest_output).strip()
    if manifest_output:
        manifest = build_dataset_manifest(records, purpose=str(args.purpose), project_name=project_name)
        manifest_path = pathlib.Path(manifest_output)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"exported {len(records)} episodes to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
