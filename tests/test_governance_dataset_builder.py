import datetime as dt

from python.helpers.governance_dataset_builder import (
    DATASET_VERSION,
    build_dataset_manifest,
    build_episode_records,
    episode_records_to_jsonl,
)


def test_build_episode_records_groups_by_run_and_sorts_events():
    events = [
        {
            "type": "run.outcome",
            "event_id": "evt-002",
            "run_id": "run-b",
            "project_name": "p1",
            "created_at": "2026-02-18T10:02:00+00:00",
            "outcome": "success",
            "consent_scope": "training_allowed",
        },
        {
            "type": "run.started",
            "event_id": "evt-001",
            "run_id": "run-b",
            "project_name": "p1",
            "created_at": "2026-02-18T10:01:00+00:00",
            "consent_scope": "training_allowed",
        },
        {
            "type": "run.started",
            "run_id": "run-a",
            "project_name": "p0",
            "created_at": "2026-02-18T09:00:00+00:00",
            "consent_scope": "eval_allowed",
        },
    ]

    records = build_episode_records(events, purpose="eval")
    assert len(records) == 2
    assert records[0]["dataset_version"] == DATASET_VERSION
    assert records[0]["run_id"] == "run-a"
    assert records[1]["run_id"] == "run-b"
    assert records[1]["events"][0]["type"] == "run.started"
    assert records[1]["events"][1]["type"] == "run.outcome"
    assert records[1]["source_event_ids"] == ["evt-001", "evt-002"]
    assert "quality_score" in records[1]["labels"]
    assert "train_eligible" in records[1]["labels"]
    assert "gold" in records[1]["labels"]


def test_build_episode_records_applies_consent_by_purpose():
    events = [
        {"type": "run.started", "run_id": "a", "consent_scope": "audit_only"},
        {"type": "run.started", "run_id": "b", "consent_scope": "eval_allowed"},
        {"type": "run.started", "run_id": "c", "consent_scope": "training_allowed"},
    ]

    eval_records = build_episode_records(events, purpose="eval")
    train_records = build_episode_records(events, purpose="training")

    assert [record["run_id"] for record in eval_records] == ["b", "c"]
    assert [record["run_id"] for record in train_records] == ["c"]


def test_episode_records_to_jsonl_is_deterministic():
    records = [
        {
            "dataset_version": DATASET_VERSION,
            "episode_id": "ep_x",
            "run_id": "run-x",
            "project_name": "p1",
            "consent_scope": "eval_allowed",
            "purpose": "eval",
            "labels": {"outcome": "unknown", "event_count": 1},
            "events": [{"type": "run.started", "run_id": "run-x"}],
        }
    ]
    payload = episode_records_to_jsonl(records)
    assert payload.count("\n") == 1
    assert "\"episode_id\": \"ep_x\"" in payload


def test_build_dataset_manifest_is_deterministic():
    records = [
        {
            "dataset_version": DATASET_VERSION,
            "episode_id": "ep_a",
            "run_id": "run-a",
            "project_name": "p1",
            "consent_scope": "eval_allowed",
            "purpose": "eval",
            "labels": {"outcome": "unknown", "event_count": 1},
            "quality": {"quality_score": 0.5, "train_eligible": True, "gold": True, "tier": "gold"},
            "source_event_ids": ["evt-100"],
            "events": [{"type": "run.started", "run_id": "run-a"}],
        }
    ]
    manifest = build_dataset_manifest(records, purpose="eval", project_name="p1")
    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["record_count"] == 1
    assert manifest["run_count"] == 1
    assert manifest["run_ids"] == ["run-a"]
    assert manifest["train_eligible_count"] == 1
    assert manifest["gold_count"] == 1
    assert manifest["source_event_count"] == 1
    assert len(str(manifest["source_event_ids_sha256"])) == 64
    assert dt.datetime.fromisoformat(str(manifest["generated_at"]))
    assert len(str(manifest["sha256"])) == 64


def test_build_episode_records_generates_stable_source_ids_without_event_id():
    events = [
        {"type": "run.started", "run_id": "run-c", "created_at": "2026-02-18T09:00:00+00:00", "consent_scope": "eval_allowed"},
        {"type": "run.outcome", "run_id": "run-c", "created_at": "2026-02-18T09:01:00+00:00", "consent_scope": "eval_allowed"},
    ]
    first = build_episode_records(events, purpose="eval")[0]["source_event_ids"]
    second = build_episode_records(events, purpose="eval")[0]["source_event_ids"]
    assert first == second
    assert all(str(item).startswith("ev_") for item in first)
