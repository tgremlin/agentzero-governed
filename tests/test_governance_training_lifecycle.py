from python.helpers.governance_training_lifecycle import (
    append_training_lifecycle_event,
    load_training_lifecycle_events,
)


def test_append_and_load_training_lifecycle_events(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "training" / "lifecycle.jsonl"
    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(lifecycle_path))

    append_training_lifecycle_event(
        {
            "event_type": "training.lifecycle",
            "stage": "trigger",
            "status": "started",
            "project_name": "p1",
        }
    )
    append_training_lifecycle_event(
        {
            "event_type": "training.lifecycle",
            "stage": "eval",
            "status": "succeeded",
            "project_name": "p1",
        }
    )

    rows = load_training_lifecycle_events(limit=10)
    assert len(rows) == 2
    assert rows[0]["stage"] == "eval"
    assert rows[1]["stage"] == "trigger"
