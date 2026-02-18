import json

from python.helpers.system_trace_store import load_system_trace_items


def test_load_system_trace_items_reads_dataset_and_training_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("A0_GOV_TRACE_DIR", str(tmp_path))

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
