#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any

from python.helpers.governance_dataset_builder import (
    build_dataset_manifest,
    build_episode_records,
    episode_records_to_jsonl,
)
from python.helpers.governance_gate import load_governance_events
from python.helpers.governance_training_dashboard import build_training_dashboard_snapshot
from python.helpers.governance_training_lifecycle import append_training_lifecycle_event
from python.helpers.system_trace_store import load_system_trace_items
from tools.governance_dataset_retention import apply_retention
from tools.governance_training_trigger import evaluate_training_trigger


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: pathlib.Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(episode_records_to_jsonl(records), encoding="utf-8")


def run_ops_cycle(
    *,
    project_name: str,
    datasets_dir: pathlib.Path,
    events_limit: int,
    min_record_count: int,
    min_gold_count: int,
    max_manifest_age_days: int,
    retention_max_age_days: int,
    retention_dry_run: bool,
) -> dict[str, Any]:
    tag = _stamp()
    project_filter = project_name or None
    events = load_governance_events(project_name=project_filter, limit=max(1, int(events_limit)))

    eval_records = build_episode_records(events, purpose="eval")
    training_records = build_episode_records(events, purpose="training")

    eval_jsonl = datasets_dir / f"dataset.{tag}.eval.jsonl"
    train_jsonl = datasets_dir / f"dataset.{tag}.training.jsonl"
    eval_manifest_path = datasets_dir / f"dataset.{tag}.eval.manifest.json"
    train_manifest_path = datasets_dir / f"dataset.{tag}.training.manifest.json"
    trigger_path = datasets_dir / f"trigger.{tag}.json"
    retention_path = datasets_dir / f"retention.{tag}.json"
    dashboard_path = datasets_dir / f"dashboard.{tag}.json"

    _write_jsonl(eval_jsonl, eval_records)
    _write_jsonl(train_jsonl, training_records)

    eval_manifest = build_dataset_manifest(eval_records, purpose="eval", project_name=project_filter)
    train_manifest = build_dataset_manifest(training_records, purpose="training", project_name=project_filter)
    _write_json(eval_manifest_path, eval_manifest)
    _write_json(train_manifest_path, train_manifest)

    trigger = evaluate_training_trigger(
        [train_manifest],
        min_record_count=max(0, int(min_record_count)),
        min_gold_count=max(0, int(min_gold_count)),
        max_manifest_age_days=max(0, int(max_manifest_age_days)),
    )
    _write_json(trigger_path, trigger)

    append_training_lifecycle_event(
        {
            "event_type": "training.trigger.decision",
            "project_name": project_name or None,
            "run_id": f"ops-cycle-{tag}",
            "stage": "trigger",
            "status": "triggered" if bool(trigger.get("trigger_training")) else "hold",
            "details": {
                "total_records": trigger.get("total_records", 0),
                "total_gold": trigger.get("total_gold", 0),
                "source": "governance_ops_cycle",
            },
        }
    )

    retention = apply_retention(
        datasets_dir,
        max_age_days=max(0, int(retention_max_age_days)),
        dry_run=bool(retention_dry_run),
    )
    _write_json(retention_path, retention)

    dashboard = build_training_dashboard_snapshot(
        load_system_trace_items(project_name=project_name),
        project_name=project_name,
    )
    _write_json(dashboard_path, dashboard)

    return {
        "ok": True,
        "tag": tag,
        "project_name": project_name or None,
        "events_count": len(events),
        "paths": {
            "eval_jsonl": str(eval_jsonl),
            "eval_manifest": str(eval_manifest_path),
            "training_jsonl": str(train_jsonl),
            "training_manifest": str(train_manifest_path),
            "trigger": str(trigger_path),
            "retention": str(retention_path),
            "dashboard": str(dashboard_path),
        },
        "summary": {
            "eval_record_count": len(eval_records),
            "training_record_count": len(training_records),
            "trigger_training": bool(trigger.get("trigger_training", False)),
            "retention_deleted": len(retention.get("deleted", [])),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run governed ops cycle: dataset exports, trigger eval, retention, and dashboard snapshot."
    )
    parser.add_argument("--project-name", default="", help="Optional governance project name filter.")
    parser.add_argument("--datasets-dir", default="/a0/usr/governance/datasets", help="Dataset artifact directory.")
    parser.add_argument("--events-limit", type=int, default=10000, help="Max governance events to read.")
    parser.add_argument("--min-record-count", type=int, default=2000, help="Trigger threshold for record count.")
    parser.add_argument("--min-gold-count", type=int, default=200, help="Trigger threshold for gold count.")
    parser.add_argument(
        "--max-manifest-age-days",
        type=int,
        default=14,
        help="Max manifest age days considered by trigger evaluation.",
    )
    parser.add_argument(
        "--retention-max-age-days",
        type=int,
        default=30,
        help="Retention max age in days for dataset artifacts.",
    )
    parser.add_argument("--retention-dry-run", action="store_true", help="Run retention without deleting files.")
    args = parser.parse_args()

    result = run_ops_cycle(
        project_name=str(args.project_name).strip(),
        datasets_dir=pathlib.Path(str(args.datasets_dir)),
        events_limit=max(1, int(args.events_limit)),
        min_record_count=max(0, int(args.min_record_count)),
        min_gold_count=max(0, int(args.min_gold_count)),
        max_manifest_age_days=max(0, int(args.max_manifest_age_days)),
        retention_max_age_days=max(0, int(args.retention_max_age_days)),
        retention_dry_run=bool(args.retention_dry_run),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
