from python.governance_runtime.audit_events import build_audit_event, sanitize_payload


def test_sanitize_payload_redacts_secrets_and_detects_pii():
    payload = {
        "tool_name": "slack:post_dm",
        "token": "xoxb-123456789012-abc123secret",
        "text": "Email me at botsheldon7@gmail.com",
    }
    result = sanitize_payload(payload)
    assert result.contains_secrets is True
    assert result.contains_pii is True
    assert result.payload["token"] == "[REDACTED_SECRET]"
    assert "[REDACTED_PII]" in result.payload["text"]


def test_build_audit_event_suppresses_payload_when_secret_detected():
    base_event = {
        "type": "tool.call.requested",
        "tool_name": "gh:pr_create",
        "tool_args": {"token": "ghp_1234567890abcdefghijklmnop"},
    }
    audit = build_audit_event(
        base_event=base_event,
        run_id="run-1",
        sequence_number=1,
        prev_event_hash="sha256:0",
    )
    assert audit["contains_secrets"] is True
    assert audit["payload_json"] == {"suppressed": True}
    assert audit["event_hash"].startswith("sha256:")


def test_build_audit_event_hash_chain_changes_with_prev_hash():
    base_event = {
        "type": "policy.check.decision",
        "tool_name": "code_execution_tool",
        "decision": "allow",
    }
    first = build_audit_event(
        base_event=base_event,
        run_id="run-2",
        sequence_number=1,
        prev_event_hash="sha256:0",
    )
    second = build_audit_event(
        base_event=base_event,
        run_id="run-2",
        sequence_number=2,
        prev_event_hash=first["event_hash"],
    )
    assert second["prev_event_hash"] == first["event_hash"]
    assert second["event_hash"] != first["event_hash"]
