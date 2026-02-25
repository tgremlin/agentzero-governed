from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from python.integrations.control_plane_adapter import ControlPlaneAdapter
from python.integrations.control_plane_client import ControlPlaneClientError
from python.integrations.control_plane_config import ControlPlaneConfig
from python.integrations.control_plane_redaction import sanitize_payload


@dataclass
class FakeContext:
    id: str = "ctx-1"
    name: str = "test"
    data: dict[str, Any] = field(default_factory=dict)

    def get_data(self, key: str, recursive: bool = True):
        _ = recursive
        return self.data.get(key)

    def set_data(self, key: str, value: Any, recursive: bool = True) -> None:
        _ = recursive
        self.data[key] = value


@dataclass
class FakeAgent:
    context: FakeContext = field(default_factory=FakeContext)
    agent_name: str = "A0"


class FakeClient:
    def __init__(self, *, tool_decisions: list[dict[str, Any]] | None = None, approval_statuses: list[str] | None = None):
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.ingested_events: list[dict[str, Any]] = []
        self.tool_decisions = list(tool_decisions or [])
        self.approval_statuses = list(approval_statuses or [])
        self.run_id = "11111111-1111-1111-1111-111111111111"

    def request_json(self, method: str, path: str, *, token: str, payload: dict[str, Any] | None = None):
        _ = token
        self.calls.append((method, path, payload))

        if method == "POST" and path == "/v1/runs":
            return 201, {"run_id": self.run_id}

        if method == "POST" and path == "/v1/events:ingest":
            events = list((payload or {}).get("events", []))
            self.ingested_events.extend(events)
            return 202, {"accepted": len(events), "rejected": 0}

        if method == "POST" and path == "/v1/runtime/tool-decisions":
            if self.tool_decisions:
                return 200, self.tool_decisions.pop(0)
            return 200, {"decision": "deny", "status": "denied"}

        if method == "GET" and path.startswith("/v1/approvals/"):
            status = self.approval_statuses.pop(0) if self.approval_statuses else "pending"
            return 200, {"approval_id": "apv-1", "status": status}

        raise AssertionError(f"unexpected request: {method} {path}")


def _config() -> ControlPlaneConfig:
    return ControlPlaneConfig(
        adapter_enabled=True,
        strict_mode=False,
        api_url="http://localhost:8080",
        deployment_id="dep-local",
        tenant_id="tenant-a",
        project_id="",
        runner_token="runner-token",
        ingestor_token="ingestor-token",
        execution_profile="standard",
        run_tag_prefix="agentzero",
        canary_correlation_tag="",
        llm_gateway_url="",
        llm_gateway_token="",
        tool_gateway_url="",
        poll_initial_seconds=0.001,
        poll_max_seconds=0.001,
        poll_timeout_seconds=0.05,
    )


def test_allow_path_executes_once_guard() -> None:
    adapter = ControlPlaneAdapter(
        FakeAgent(),
        config=_config(),
        client=FakeClient(tool_decisions=[{"decision": "allow", "status": "executed"}]),
    )

    result = adapter.decide_tool(tool_name="search_engine", tool_args={"q": "test"}, action="tool:search_engine", risk="low")

    assert result.decision == "allow"
    call_hash = adapter.compute_tool_call_hash("search_engine", {"q": "test"})
    assert adapter.mark_tool_executed_once(call_hash) is True
    assert adapter.mark_tool_executed_once(call_hash) is False


def test_hold_then_approve_wait_loop() -> None:
    client = FakeClient(
        tool_decisions=[{"decision": "require_approval", "status": "held", "approval_id": "apv-1"}],
        approval_statuses=["pending", "approved"],
    )
    adapter = ControlPlaneAdapter(FakeAgent(), config=_config(), client=client)

    result = adapter.decide_tool(tool_name="code_execution_tool", tool_args={"runtime": "terminal"}, action="tool:code_execution_tool", risk="critical")
    status = adapter.wait_for_approval(result.approval_id)

    assert result.decision == "require_approval"
    assert status == "approved"


def test_deny_path_no_execution() -> None:
    adapter = ControlPlaneAdapter(
        FakeAgent(),
        config=_config(),
        client=FakeClient(tool_decisions=[{"decision": "deny", "status": "denied"}]),
    )

    result = adapter.decide_tool(tool_name="input", tool_args={"value": "x"}, action="tool:input", risk="high")

    assert result.decision == "deny"
    assert result.status == "denied"


def test_event_emission_sequence_monotonic() -> None:
    client = FakeClient()
    adapter = ControlPlaneAdapter(FakeAgent(), config=_config(), client=client)

    adapter.ensure_run_started()
    adapter.emit_event("tool.decision.requested", {"tool_name": "search_engine"})
    adapter.emit_event("tool.executed", {"tool_name": "search_engine"})

    seqs = [int(e["sequence_number"]) for e in client.ingested_events]
    event_types = [str(e["event_type"]) for e in client.ingested_events]

    assert seqs == sorted(seqs)
    assert seqs == [1, 2, 3, 4]
    assert event_types == ["run.started", "run.correlation", "tool.decision.requested", "tool.executed"]


def test_duplicate_approval_observation_does_not_double_execute() -> None:
    client = FakeClient(
        tool_decisions=[{"decision": "require_approval", "status": "held", "approval_id": "apv-1"}],
        approval_statuses=["approved", "approved"],
    )
    adapter = ControlPlaneAdapter(FakeAgent(), config=_config(), client=client)
    result = adapter.decide_tool(
        tool_name="code_execution_tool",
        tool_args={"runtime": "terminal", "cmd": "echo hi"},
        action="tool:code_execution_tool",
        risk="critical",
    )
    call_hash = adapter.compute_tool_call_hash("code_execution_tool", {"runtime": "terminal", "cmd": "echo hi"})

    status_1 = adapter.wait_for_approval(result.approval_id)
    execute_1 = False
    if status_1 == "approved" and adapter.mark_approval_consumed_once(result.approval_id):
        execute_1 = adapter.mark_tool_executed_once(call_hash)

    status_2 = adapter.wait_for_approval(result.approval_id)
    execute_2 = False
    if status_2 == "approved" and adapter.mark_approval_consumed_once(result.approval_id):
        execute_2 = adapter.mark_tool_executed_once(call_hash)

    assert execute_1 is True
    assert execute_2 is False


def test_strict_mode_rejects_shared_runner_and_ingestor_tokens() -> None:
    cfg = ControlPlaneConfig(
        adapter_enabled=True,
        strict_mode=True,
        api_url="http://localhost:8080",
        deployment_id="dep-local",
        tenant_id="tenant-a",
        project_id="",
        runner_token="same-token",
        ingestor_token="same-token",
        execution_profile="standard",
        run_tag_prefix="agentzero",
        canary_correlation_tag="",
        llm_gateway_url="",
        llm_gateway_token="",
        tool_gateway_url="",
        poll_initial_seconds=0.001,
        poll_max_seconds=0.001,
        poll_timeout_seconds=0.05,
    )
    try:
        ControlPlaneAdapter(FakeAgent(), config=cfg, client=FakeClient())
    except ControlPlaneClientError as exc:
        assert "CP_INGESTOR_TOKEN(distinct-from-runner)" in str(exc)
    else:
        raise AssertionError("expected strict mode adapter init to fail")


def test_redaction_masks_sensitive_keys_but_preserves_shape() -> None:
    payload = {
        "token": "abc",
        "nested": {"password": "secret", "ok": "visible"},
        "api_key": "k",
        "access_token": "t",
        "non_sensitive": 7,
    }
    redacted = sanitize_payload(payload)

    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["nested"]["ok"] == "visible"
    assert redacted["non_sensitive"] == 7
