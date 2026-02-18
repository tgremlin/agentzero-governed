import json

from python.helpers.system_trace_store import load_system_trace_items


def test_load_system_trace_items_reads_dataset_and_training_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(tmp_path / "training-lifecycle.jsonl"))

    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "exports" / "dataset.manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-02-18T10:00:00+00:00",
                "project_name": "p1",
                "purpose": "training",
                "record_count": 10,
                "gold_count": 2,
                "source_event_count": 30,
                "sha256": "abc",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "exports" / "run-trigger-plan.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-02-18T10:01:00+00:00",
                "trigger_training": True,
                "eligible_manifests": 1,
                "total_records": 10,
                "total_gold": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    items = load_system_trace_items()
    assert len(items) == 2
    assert items[0]["kind"] == "training_decisions"
    assert items[1]["kind"] == "dataset_exports"

    datasets = load_system_trace_items(type_filter="dataset_exports")
    assert len(datasets) == 1
    assert datasets[0]["project_name"] == "p1"


def test_load_system_trace_items_includes_training_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(tmp_path))
    lifecycle = tmp_path / "training-lifecycle.jsonl"
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(lifecycle))
    lifecycle.write_text(
        json.dumps(
            {
                "event_ts": "2026-02-18T10:02:00+00:00",
                "event_type": "training.lifecycle",
                "stage": "eval",
                "status": "succeeded",
                "project_name": "p1",
                "run_id": "run-1",
                "details": {"score": 0.91},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_system_trace_items(type_filter="training_lifecycle")
    assert len(rows) == 1
    assert rows[0]["stage"] == "eval"
    assert rows[0]["status"] == "succeeded"
