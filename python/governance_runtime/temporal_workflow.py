from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from python.governance_runtime.repos import get_postgres_repo


@dataclass
class GovernedRunInput:
    run_id: str
    context_id: str
    project_name: str | None = None


@activity.defn
async def persist_run_started(input_data: GovernedRunInput) -> None:
    repo = get_postgres_repo()
    if repo is None:
        return

    repo.ensure_run(
        run_id=input_data.run_id,
        context_id=input_data.context_id,
        project_name=input_data.project_name,
        status="running",
    )
    repo.append_event(
        {
            "type": "run.started",
            "run_id": input_data.run_id,
            "context_id": input_data.context_id,
            "project_name": input_data.project_name,
            "status": "running",
        }
    )


@activity.defn
async def persist_run_signal(
    run_id: str, signal: str, status: str, payload: dict[str, Any] | None = None
) -> None:
    repo = get_postgres_repo()
    if repo is None:
        return

    repo.update_run_status(run_id=run_id, status=status)
    repo.append_event(
        {
            "type": "run.signaled",
            "run_id": run_id,
            "signal": signal,
            "status": status,
            "payload": payload or {},
        }
    )


@workflow.defn
class GovernedRunWorkflow:
    def __init__(self) -> None:
        self._status = "queued"
        self._signals: list[tuple[str, dict[str, Any]]] = []
        self._cancelled = False

    @workflow.run
    async def run(self, input_data: GovernedRunInput) -> dict[str, Any]:
        await workflow.execute_activity(
            persist_run_started,
            input_data,
            start_to_close_timeout=timedelta(seconds=15),
        )
        self._status = "running"

        while not self._cancelled:
            await workflow.wait_condition(lambda: self._cancelled or len(self._signals) > 0)

            while self._signals:
                signal, payload = self._signals.pop(0)
                if signal == "pause":
                    self._status = "paused"
                elif signal == "resume":
                    self._status = "running"
                elif signal == "cancel":
                    self._status = "cancelled"
                    self._cancelled = True

                await workflow.execute_activity(
                    persist_run_signal,
                    args=[input_data.run_id, signal, self._status, payload],
                    start_to_close_timeout=timedelta(seconds=15),
                )

        return {"run_id": input_data.run_id, "status": self._status}

    @workflow.signal
    def pause(self, payload: dict[str, Any] | None = None) -> None:
        self._signals.append(("pause", payload or {}))

    @workflow.signal
    def resume(self, payload: dict[str, Any] | None = None) -> None:
        self._signals.append(("resume", payload or {}))

    @workflow.signal
    def cancel(self, payload: dict[str, Any] | None = None) -> None:
        self._signals.append(("cancel", payload or {}))

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        return {"status": self._status}
