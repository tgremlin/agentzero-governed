from __future__ import annotations

import threading

from python.api.governance_events import GovernanceEvents
from python.api.governance_run_signal import GovernanceRunSignal
from python.api.governance_run_start import GovernanceRunStart
from python.api.system_trace import SystemTrace
from python.api.training_candidates import TrainingCandidates
from python.api.training_candidates_update import TrainingCandidatesUpdate


class _DummyContext:
    def __init__(self, ctxid: str) -> None:
        self.id = ctxid


def test_governance_run_start_disabled_returns_409(monkeypatch):
    import python.api.governance_run_start as mod

    handler = GovernanceRunStart(None, threading.Lock())
    monkeypatch.setattr(mod, "is_temporal_enabled", lambda: False)

    resp = __import__("asyncio").run(handler.process({}, None))

    assert getattr(resp, "status_code", None) == 409


def test_governance_run_start_success(monkeypatch):
    import python.api.governance_run_start as mod

    handler = GovernanceRunStart(None, threading.Lock())
    dummy = _DummyContext("ctx_1")

    monkeypatch.setattr(mod, "is_temporal_enabled", lambda: True)
    monkeypatch.setattr(handler, "use_context", lambda _ctxid: dummy)
    monkeypatch.setattr(mod.projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(
        mod,
        "start_governed_run",
        lambda **_kwargs: {"run_id": "r1", "status": "queued", "persisted": True},
    )

    out = __import__("asyncio").run(handler.process({"context_id": "ctx_1"}, None))

    assert out["ok"] is True
    assert out["run_id"] == "r1"
    assert out["project_name"] == "p1"


def test_governance_run_signal_validation_and_success(monkeypatch):
    import python.api.governance_run_signal as mod

    handler = GovernanceRunSignal(None, threading.Lock())
    monkeypatch.setattr(mod, "is_temporal_enabled", lambda: True)

    bad = __import__("asyncio").run(handler.process({"run_id": "r1", "signal": "bogus"}, None))
    assert getattr(bad, "status_code", None) == 400

    monkeypatch.setattr(
        mod,
        "signal_governed_run",
        lambda **_kwargs: {"run_id": "r1", "signal": "pause", "status": "paused", "persisted": True},
    )
    ok = __import__("asyncio").run(handler.process({"run_id": "r1", "signal": "pause"}, None))
    assert ok["ok"] is True
    assert ok["status"] == "paused"


def test_governance_events_reads_by_context(monkeypatch):
    import python.api.governance_events as mod

    handler = GovernanceEvents(None, threading.Lock())
    dummy = _DummyContext("ctx_1")

    monkeypatch.setattr(handler, "use_context", lambda _ctxid, create_if_not_exists=False: dummy)
    monkeypatch.setattr(mod.projects, "get_context_project_name", lambda _ctx: "p1")
    monkeypatch.setattr(
        mod,
        "load_governance_events",
        lambda project_name=None, limit=200: [{"type": "run.started", "project_name": project_name, "limit": limit}],
    )

    out = __import__("asyncio").run(handler.process({"context_id": "ctx_1", "limit": 25}, None))

    assert out["ok"] is True
    assert out["project_name"] == "p1"
    assert out["count"] == 1
    assert out["events"][0]["type"] == "run.started"


def test_governance_events_filters_and_export(monkeypatch):
    import python.api.governance_events as mod

    handler = GovernanceEvents(None, threading.Lock())
    events = [
        {
            "type": "approval.requested",
            "status": "pending",
            "project_name": "p1",
            "run_id": "r1",
            "created_at": "2026-02-17T10:00:00+00:00",
            "tool_name": "code_execution_tool",
        },
        {
            "type": "approval.resolved",
            "status": "approved",
            "project_name": "p1",
            "run_id": "r1",
            "created_at": "2026-02-17T10:01:00+00:00",
            "tool_name": "code_execution_tool",
        },
    ]
    monkeypatch.setattr(mod, "load_governance_events", lambda project_name=None, limit=200: events)

    filtered = __import__("asyncio").run(
        handler.process(
            {
                "project_name": "p1",
                "event_type": "approval.requested",
                "status": "pending",
                "q": "code_execution_tool",
            },
            None,
        )
    )
    assert filtered["count"] == 1
    assert filtered["total"] == 1

    csv_resp = __import__("asyncio").run(
        handler.process({"project_name": "p1", "export_format": "csv", "limit": 10}, None)
    )
    assert getattr(csv_resp, "status_code", None) == 200
    assert "text/csv" in str(getattr(csv_resp, "mimetype", ""))
    assert "approval.requested" in csv_resp.get_data(as_text=True)

    jsonl_resp = __import__("asyncio").run(
        handler.process({"project_name": "p1", "export_format": "jsonl", "limit": 10}, None)
    )
    assert getattr(jsonl_resp, "status_code", None) == 200
    assert "application/x-ndjson" in str(getattr(jsonl_resp, "mimetype", ""))
    assert "\"approval.resolved\"" in jsonl_resp.get_data(as_text=True)


def test_training_candidates_filter_and_export(monkeypatch):
    import python.api.training_candidates as mod

    handler = TrainingCandidates(None, threading.Lock())
    events = [
        {
            "type": "approval.resolved",
            "status": "approved",
            "project_name": "p1",
            "run_id": "r1",
            "created_at": "2026-02-17T10:01:00+00:00",
            "tool_name": "code_execution_tool",
        },
        {
            "type": "approval.resolved",
            "status": "denied",
            "project_name": "p1",
            "run_id": "r2",
            "created_at": "2026-02-17T10:02:00+00:00",
            "tool_name": "code_execution_tool",
        },
    ]
    monkeypatch.setattr(mod, "load_governance_events", lambda project_name=None, limit=200: events)

    out = __import__("asyncio").run(
        handler.process({"project_name": "p1", "training_status": "ready"}, None)
    )
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["items"][0]["training_status"] == "ready"

    csv_resp = __import__("asyncio").run(
        handler.process({"project_name": "p1", "export_format": "csv", "limit": 10}, None)
    )
    assert getattr(csv_resp, "status_code", None) == 200
    assert "text/csv" in str(getattr(csv_resp, "mimetype", ""))
    assert "candidate_id" in csv_resp.get_data(as_text=True)


def test_system_trace_scaffold_contract():
    handler = SystemTrace(None, threading.Lock())
    out = __import__("asyncio").run(handler.process({}, None))
    assert out["ok"] is True
    assert out["coming_soon"] is True
    assert isinstance(out.get("types"), list)


def test_training_candidates_update_and_override(monkeypatch):
    import python.api.training_candidates as candidates_mod
    import python.api.training_candidates_update as update_mod

    event = {
        "type": "approval.resolved",
        "status": "approved",
        "project_name": "p1",
        "run_id": "r1",
        "created_at": "2026-02-17T10:01:00+00:00",
        "tool_name": "code_execution_tool",
    }
    monkeypatch.setattr(candidates_mod, "load_governance_events", lambda project_name=None, limit=200: [event])

    override_state = {}

    def _load_state(_project_name):
        return dict(override_state)

    def _save_state(_project_name, items):
        override_state.clear()
        override_state.update(items)

    monkeypatch.setattr(update_mod, "bulk_update_candidates", __import__("python.helpers.training_candidates_store", fromlist=["bulk_update_candidates"]).bulk_update_candidates)
    monkeypatch.setattr(candidates_mod, "apply_candidate_overrides", __import__("python.helpers.training_candidates_store", fromlist=["apply_candidate_overrides"]).apply_candidate_overrides)
    monkeypatch.setattr("python.helpers.training_candidates_store.load_candidate_overrides", _load_state, raising=False)
    monkeypatch.setattr("python.helpers.training_candidates_store.save_candidate_overrides", _save_state, raising=False)

    # Use helper-level functions directly for deterministic check
    from python.helpers.training_candidates_store import bulk_update_candidates

    cid = candidates_mod._candidate_from_event(event)["candidate_id"]  # type: ignore[index]
    out = bulk_update_candidates("p1", [cid], training_status="exclude", note="manual")
    assert out["updated"] == 1

    update_handler = TrainingCandidatesUpdate(None, threading.Lock())
    ok = __import__("asyncio").run(
        update_handler.process(
            {
                "project_name": "p1",
                "candidate_ids": [cid],
                "action": "mark_ready",
                "note": "approved after audit",
            },
            None,
        )
    )
    assert ok["ok"] is True
    assert ok["training_status"] == "ready"
