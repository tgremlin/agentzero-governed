import json
from pathlib import Path

from tools.governance_ops_cycle import run_ops_cycle


def test_run_ops_cycle_writes_expected_artifacts(tmp_path: Path, monkeypatch):
    gov_dir = tmp_path / "governance"
    events_dir = gov_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("A0_GOVERNANCE_DIR", str(gov_dir))
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(tmp_path / "datasets" / "training-lifecycle.jsonl"))
    monkeypatch.setenv("GOV_PERSIST_BACKEND", "file")

    event = {
        "event_id": "ev-1",
        "type": "run.started",
        "run_id": "run-1",
        "project_name": "p1",
        "created_at": "2026-02-19T12:00:00+00:00",
        "consent_scope": "training_allowed",
        "actor_id": "actor_agent_runtime",
        "actor_type": "agent",
    }
    (events_dir / "events-20260219.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    out = run_ops_cycle(
        project_name="p1",
        datasets_dir=tmp_path / "datasets",
        events_limit=100,
        min_record_count=1,
        min_gold_count=0,
        max_manifest_age_days=30,
        retention_max_age_days=365,
        retention_dry_run=True,
    )
    assert out["ok"] is True
    assert out["summary"]["trigger_training"] is True
    for path in out["paths"].values():
        assert Path(path).exists()


def test_run_ops_cycle_holds_trigger_without_training_records(tmp_path: Path, monkeypatch):
    gov_dir = tmp_path / "governance"
    events_dir = gov_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("A0_GOVERNANCE_DIR", str(gov_dir))
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(tmp_path / "datasets" / "training-lifecycle.jsonl"))
    monkeypatch.setenv("GOV_PERSIST_BACKEND", "file")

    event = {
        "event_id": "ev-2",
        "type": "run.started",
        "run_id": "run-2",
        "project_name": "p1",
        "created_at": "2026-02-19T12:00:00+00:00",
        "consent_scope": "eval_allowed",
        "actor_id": "actor_agent_runtime",
        "actor_type": "agent",
    }
    (events_dir / "events-20260219.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    out = run_ops_cycle(
        project_name="p1",
        datasets_dir=tmp_path / "datasets",
        events_limit=100,
        min_record_count=1,
        min_gold_count=0,
        max_manifest_age_days=30,
        retention_max_age_days=365,
        retention_dry_run=True,
    )
    assert out["ok"] is True
    assert out["summary"]["trigger_training"] is False
