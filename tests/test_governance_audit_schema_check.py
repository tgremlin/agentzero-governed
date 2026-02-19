from python.governance_runtime.audit_events import SCHEMA_VERSION, TAXONOMY_VERSION
from tools.governance_audit_schema_check import evaluate_event_schema_health


def _event(**overrides):
    base = {
        "event_id": "e1",
        "event_type": "run.started",
        "run_id": "r1",
        "actor_id": "actor_agent_runtime",
        "actor_type": "agent",
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    base.update(overrides)
    return base


def test_audit_schema_check_passes_for_valid_events():
    report = evaluate_event_schema_health([_event(), _event(event_id="e2")], require_events=True)
    assert report["ok"] is True
    assert report["event_count"] == 2
    assert all(item["ok"] for item in report["checks"])


def test_audit_schema_check_fails_for_missing_required_and_version_mismatch():
    bad = _event(
        event_id="",
        schema_version="0.9.0",
        taxonomy_version="2025.01.01",
    )
    report = evaluate_event_schema_health([bad], require_events=True)
    assert report["ok"] is False
    details = {item["name"]: item for item in report["checks"]}
    assert details["required_fields"]["ok"] is False
    assert details["schema_version"]["ok"] is False
    assert details["taxonomy_version"]["ok"] is False
