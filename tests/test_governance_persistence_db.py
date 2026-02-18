from __future__ import annotations

from pathlib import Path

from python.helpers import governance_gate


class _DummyLog:
    def log(self, **_kwargs):
        return self


class _DummyContext:
    def __init__(self) -> None:
        self.paused = False
        self.log = _DummyLog()


class _DummyAgent:
    def __init__(self) -> None:
        self.context = _DummyContext()


class _FakeRepo:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []
        self.events: list[dict] = []
        self.status = "pending"

    def upsert_approval(self, payload: dict) -> None:
        self.upsert_calls.append(payload)

    def get_approval_status(self, _approval_id: str) -> str:
        return self.status

    def append_event(self, event: dict) -> None:
        self.events.append(event)

    def load_approvals(self, project_name: str | None = None, limit: int = 200):
        return [{"approval_id": "apv_repo", "project_name": project_name, "limit": limit}]

    def load_events(self, project_name: str | None = None, limit: int = 200):
        return [{"type": "approval.requested", "project_name": project_name, "limit": limit}]


def _policy_enabled_require_approval():
    return {
        "project_name": "p1",
        "governance_enabled": True,
        "mode": "standard",
        "require_approval_for": ["high", "critical"],
        "allow_readonly_terminal_without_approval": False,
        "tool_overrides": {},
        "default_policy": "allow",
    }


def test_postgres_backend_writes_repo_only_when_dual_write_disabled(monkeypatch, tmp_path: Path):
    fake_repo = _FakeRepo()
    monkeypatch.setattr(governance_gate, "_resolve_governance_storage_dir", lambda: tmp_path)
    monkeypatch.setattr(governance_gate, "_load_project_governance", lambda _agent: _policy_enabled_require_approval())
    monkeypatch.setattr(governance_gate, "is_postgres_backend_enabled", lambda: True)
    monkeypatch.setattr(governance_gate, "get_postgres_repo", lambda: fake_repo)
    monkeypatch.setattr(governance_gate, "is_dual_write_enabled", lambda: False)
    monkeypatch.setattr(governance_gate, "get_persist_backend", lambda: "postgres")

    agent = _DummyAgent()
    result = governance_gate.evaluate_tool_gate(
        agent,
        "code_execution_tool",
        {"runtime": "terminal", "code": "touch /tmp/hi"},
    )

    assert result["decision"] == "require_approval"
    assert len(fake_repo.upsert_calls) == 1
    event_types = [str(e.get("type", "")) for e in fake_repo.events]
    assert "approval.requested" in event_types
    assert "policy.check.decision" in event_types
    assert not (tmp_path / "approvals").exists()


def test_postgres_backend_dual_write_keeps_file_mirror(monkeypatch, tmp_path: Path):
    fake_repo = _FakeRepo()
    monkeypatch.setattr(governance_gate, "_resolve_governance_storage_dir", lambda: tmp_path)
    monkeypatch.setattr(governance_gate, "_load_project_governance", lambda _agent: _policy_enabled_require_approval())
    monkeypatch.setattr(governance_gate, "is_postgres_backend_enabled", lambda: True)
    monkeypatch.setattr(governance_gate, "get_postgres_repo", lambda: fake_repo)
    monkeypatch.setattr(governance_gate, "is_dual_write_enabled", lambda: True)
    monkeypatch.setattr(governance_gate, "get_persist_backend", lambda: "postgres")

    agent = _DummyAgent()
    governance_gate.evaluate_tool_gate(
        agent,
        "code_execution_tool",
        {"runtime": "terminal", "code": "touch /tmp/hi"},
    )

    approvals = list((tmp_path / "approvals").glob("apv_*.json"))
    assert approvals
    assert len(fake_repo.upsert_calls) == 1


def test_snapshot_load_prefers_repo_when_postgres_enabled(monkeypatch):
    fake_repo = _FakeRepo()
    monkeypatch.setattr(governance_gate, "is_postgres_backend_enabled", lambda: True)
    monkeypatch.setattr(governance_gate, "get_postgres_repo", lambda: fake_repo)

    approvals = governance_gate.load_governance_approvals(project_name="p1", limit=25)
    events = governance_gate.load_governance_events(project_name="p1", limit=25)

    assert approvals == [{"approval_id": "apv_repo", "project_name": "p1", "limit": 25}]
    assert events == [{"type": "approval.requested", "project_name": "p1", "limit": 25}]
