import json
import sys
from pathlib import Path

import tools.governance_training_dashboard as dashboard_mod
from python.helpers.governance_training_dashboard import build_training_dashboard_snapshot


def test_build_training_dashboard_snapshot_computes_expected_values():
    items = [
        {
            "kind": "dataset_exports",
            "project_name": "alpha",
            "record_count": 100,
            "gold_count": 25,
            "generated_at": "2026-02-18T10:00:00Z",
        },
        {
            "kind": "dataset_exports",
            "project_name": "alpha",
            "record_count": 40,
            "gold_count": 20,
            "generated_at": "2026-02-18T11:00:00Z",
        },
        {
            "kind": "training_decisions",
            "project_name": "alpha",
            "decision": "trigger",
            "generated_at": "2026-02-18T11:10:00Z",
        },
        {
            "kind": "training_decisions",
            "project_name": "alpha",
            "decision": "canary",
            "generated_at": "2026-02-18T11:20:00Z",
        },
        {
            "kind": "training_lifecycle",
            "project_name": "alpha",
            "stage": "eval",
            "status": "started",
            "run_id": "run-1",
            "generated_at": "2026-02-18T11:30:00Z",
        },
        {
            "kind": "training_lifecycle",
            "project_name": "alpha",
            "stage": "eval",
            "status": "success",
            "run_id": "run-2",
            "generated_at": "2026-02-18T11:40:00Z",
        },
        {
            "kind": "dataset_exports",
            "project_name": "beta",
            "record_count": 999,
            "gold_count": 999,
            "generated_at": "2026-02-18T00:00:00Z",
        },
    ]

    out = build_training_dashboard_snapshot(items, project_name="alpha")
    assert out["sources"]["dataset_exports"] == 2
    assert out["dataset_summary"]["total_records"] == 140
    assert out["dataset_summary"]["total_gold"] == 45
    assert out["dataset_summary"]["gold_yield"] == round(45 / 140, 6)
    assert out["decision_summary"]["by_decision"]["trigger"] == 1
    assert out["decision_summary"]["by_decision"]["canary"] == 1
    assert out["lifecycle_summary"]["stage_status_counts"]["eval"]["started"] == 1
    assert out["lifecycle_summary"]["active_run_count"] == 1


def test_governance_training_dashboard_cli_outputs_snapshot(tmp_path: Path, monkeypatch):
    trace_dir = tmp_path / "datasets"
    trace_dir.mkdir(parents=True, exist_ok=True)

    (trace_dir / "alpha-01.manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-02-18T10:00:00Z",
                "project_name": "alpha",
                "purpose": "training",
                "record_count": 20,
                "gold_count": 10,
                "source_event_count": 20,
                "sha256": "abc",
            }
        ),
        encoding="utf-8",
    )
    (trace_dir / "alpha-trigger.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-02-18T10:05:00Z",
                "decision": "trigger",
                "total_records": 20,
                "total_gold": 10,
            }
        ),
        encoding="utf-8",
    )
    lifecycle = tmp_path / "training-lifecycle.jsonl"
    lifecycle.write_text(
        json.dumps(
            {
                "event_ts": "2026-02-18T10:06:00Z",
                "event_type": "training.lifecycle",
                "project_name": "alpha",
                "stage": "trigger",
                "status": "started",
                "run_id": "run-1",
                "details": {"source": "test"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out_path = tmp_path / "dashboard.json"
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(trace_dir))
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(lifecycle))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_training_dashboard.py",
            "--project-name",
            "alpha",
            "--output",
            str(out_path),
        ],
    )

    rc = dashboard_mod.main()
    assert rc == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["sources"]["dataset_exports"] == 1
    assert payload["decision_summary"]["by_decision"]["trigger"] == 1
    assert payload["lifecycle_summary"]["active_run_count"] == 1


def test_build_training_dashboard_snapshot_treats_promote_as_terminal():
    items = [
        {
            "kind": "training_lifecycle",
            "project_name": "alpha",
            "stage": "promotion",
            "status": "promote",
            "run_id": "run-1",
            "generated_at": "2026-02-18T11:30:00Z",
        }
    ]
    out = build_training_dashboard_snapshot(items, project_name="alpha")
    assert out["lifecycle_summary"]["active_run_count"] == 0
