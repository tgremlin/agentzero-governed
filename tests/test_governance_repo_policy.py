from python.governance_runtime.repos import _build_policy_decision_record


def test_build_policy_decision_record_maps_valid_event():
    event = {
        "type": "policy.check.decision",
        "decision": "require_approval",
        "reason_codes": ["risk.high", "override.none"],
        "policy_name": "governance_gate",
        "policy_version": "v1",
    }
    audit_event = {
        "event_id": "evt-1",
        "event_type": "policy.check.decision",
        "tenant_id": "tenant-a",
        "run_id": "run-a",
        "sequence_number": 12,
        "observed_at": "2026-02-18T00:00:00+00:00",
    }

    record = _build_policy_decision_record(event=event, audit_event=audit_event)

    assert record is not None
    assert record["event_id"] == "evt-1"
    assert record["tenant_id"] == "tenant-a"
    assert record["run_id"] == "run-a"
    assert record["sequence_number"] == 12
    assert record["decision"] == "require_approval"
    assert record["reason_codes"] == ["risk.high", "override.none"]


def test_build_policy_decision_record_rejects_non_policy_events():
    event = {"type": "approval.requested", "decision": "allow"}
    audit_event = {"event_type": "approval.requested"}
    assert _build_policy_decision_record(event=event, audit_event=audit_event) is None


def test_build_policy_decision_record_rejects_unknown_decision():
    event = {"type": "policy.check.decision", "decision": "maybe"}
    audit_event = {"event_type": "policy.check.decision"}
    assert _build_policy_decision_record(event=event, audit_event=audit_event) is None
