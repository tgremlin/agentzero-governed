from __future__ import annotations

import asyncio

from python.governance_runtime import temporal_client


class _FakeRepo:
    def __init__(self) -> None:
        self.created: list[tuple[str, str | None, str]] = []
        self.updated: list[tuple[str, str]] = []
        self.events: list[dict] = []

    def create_run(self, context_id: str, project_name: str | None = None, status: str = "queued") -> str:
        self.created.append((context_id, project_name, status))
        return "11111111-1111-1111-1111-111111111111"

    def update_run_status(self, run_id: str, status: str) -> None:
        self.updated.append((run_id, status))

    def append_event(self, event: dict) -> None:
        self.events.append(event)


def test_temporal_enabled_flag(monkeypatch):
    monkeypatch.setenv("GOV_TEMPORAL_ENABLED", "true")
    assert temporal_client.is_temporal_enabled() is True

    monkeypatch.setenv("GOV_TEMPORAL_ENABLED", "false")
    assert temporal_client.is_temporal_enabled() is False


def test_start_governed_run_persists_when_repo_available(monkeypatch):
    repo = _FakeRepo()
    monkeypatch.setattr(temporal_client, "get_postgres_repo", lambda: repo)

    out = asyncio.run(temporal_client.start_governed_run(context_id="ctx_1", project_name="p1"))

    assert out["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert out["status"] == "queued"
    assert out["persisted"] is True
    assert repo.created == [("ctx_1", "p1", "queued")]
    assert repo.events and repo.events[0]["type"] == "run.started"


def test_signal_governed_run_updates_status_and_event(monkeypatch):
    repo = _FakeRepo()
    monkeypatch.setattr(temporal_client, "get_postgres_repo", lambda: repo)

    out = asyncio.run(
        temporal_client.signal_governed_run(
            run_id="11111111-1111-1111-1111-111111111111",
            signal="pause",
            payload={"reason": "manual"},
        )
    )

    assert out["status"] == "paused"
    assert out["persisted"] is True
    assert repo.updated == [("11111111-1111-1111-1111-111111111111", "paused")]
    assert repo.events and repo.events[0]["type"] == "run.signaled"
