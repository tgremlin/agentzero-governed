import json
import sys
from pathlib import Path

import tools.governance_dataset_export as export_mod


def _run_export(monkeypatch, tmp_path: Path, purpose: str) -> tuple[list[dict], dict]:
    events = [
        {
            "type": "run.started",
            "event_id": "evt-a",
            "run_id": "run-a",
            "project_name": "proj",
            "created_at": "2026-02-18T10:00:00+00:00",
            "consent_scope": "audit_only",
        },
        {
            "type": "run.started",
            "event_id": "evt-b",
            "run_id": "run-b",
            "project_name": "proj",
            "created_at": "2026-02-18T10:01:00+00:00",
            "consent_scope": "eval_allowed",
        },
        {
            "type": "run.started",
            "event_id": "evt-c",
            "run_id": "run-c",
            "project_name": "proj",
            "created_at": "2026-02-18T10:02:00+00:00",
            "consent_scope": "training_allowed",
        },
    ]
    monkeypatch.setattr(export_mod, "load_governance_events", lambda **kwargs: events)

    output = tmp_path / f"{purpose}.jsonl"
    manifest = tmp_path / f"{purpose}.manifest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_dataset_export.py",
            "--project-name",
            "proj",
            "--purpose",
            purpose,
            "--output",
            str(output),
            "--manifest-output",
            str(manifest),
        ],
    )
    rc = export_mod.main()
    assert rc == 0

    rows = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    return rows, manifest_payload


def test_dataset_export_eval_respects_consent_and_lineage(monkeypatch, tmp_path: Path):
    rows, manifest = _run_export(monkeypatch, tmp_path, purpose="eval")
    assert [row["run_id"] for row in rows] == ["run-b", "run-c"]
    assert rows[0]["source_event_ids"] == ["evt-b"]
    assert rows[1]["source_event_ids"] == ["evt-c"]
    assert manifest["purpose"] == "eval"
    assert manifest["source_event_count"] == 2
    assert len(str(manifest["source_event_ids_sha256"])) == 64


def test_dataset_export_training_respects_consent(monkeypatch, tmp_path: Path):
    rows, manifest = _run_export(monkeypatch, tmp_path, purpose="training")
    assert [row["run_id"] for row in rows] == ["run-c"]
    assert rows[0]["source_event_ids"] == ["evt-c"]
    assert manifest["purpose"] == "training"
    assert manifest["record_count"] == 1
