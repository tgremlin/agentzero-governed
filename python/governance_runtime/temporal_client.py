from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

try:
    from temporalio.client import Client
except Exception:  # pragma: no cover - optional in environments without Temporal SDK
    Client = None  # type: ignore[assignment]

from python.governance_runtime.repos import get_postgres_repo
from python.governance_runtime.event_taxonomy import EVENT_RUN_OUTCOME


_RUN_STATUS_BY_SIGNAL = {
    "pause": "paused",
    "resume": "running",
    "cancel": "cancelled",
}

_CLIENT: Any = None
_CLIENT_LOCK = asyncio.Lock()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def is_temporal_enabled() -> bool:
    return _env_flag("GOV_TEMPORAL_ENABLED", default=False)


async def _get_client() -> Client:
    if Client is None:
        raise RuntimeError("temporalio is not installed")
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    async with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT

        host = os.environ.get("TEMPORAL_HOST", "temporal:7233")
        namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
        _CLIENT = await Client.connect(host, namespace=namespace)
        return _CLIENT


def _db_fallback_start(*, context_id: str, project_name: str | None) -> dict[str, Any]:
    repo = get_postgres_repo()
    run_id = str(uuid.uuid4())
    persisted = False
    if repo is not None:
        try:
            run_id = repo.create_run(context_id=context_id, project_name=project_name, status="queued")
            repo.append_event(
                {
                    "type": "run.started",
                    "run_id": run_id,
                    "context_id": context_id,
                    "project_name": project_name,
                    "status": "queued",
                }
            )
            persisted = True
        except Exception:
            persisted = False

    return {
        "run_id": run_id,
        "status": "queued",
        "persisted": persisted,
        "temporal": False,
    }


def _db_fallback_signal(*, run_id: str, signal: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    sig = str(signal or "").strip().lower()
    if sig not in {"pause", "resume", "cancel"}:
        raise ValueError(f"unsupported signal: {signal}")

    repo = get_postgres_repo()
    persisted = False
    status = _RUN_STATUS_BY_SIGNAL[sig]
    if repo is not None:
        try:
            repo.update_run_status(run_id=run_id, status=status)
            repo.append_event(
                {
                    "type": "run.signaled",
                    "run_id": run_id,
                    "signal": sig,
                    "status": status,
                    "payload": payload or {},
                }
            )
            if sig == "cancel":
                repo.append_event(
                    {
                        "type": EVENT_RUN_OUTCOME,
                        "run_id": run_id,
                        "outcome": "cancelled",
                        "status": status,
                        "source": "temporal_client_fallback",
                    }
                )
            persisted = True
        except Exception:
            persisted = False

    return {
        "run_id": run_id,
        "signal": sig,
        "status": status,
        "persisted": persisted,
        "temporal": False,
    }


async def start_governed_run(*, context_id: str, project_name: str | None) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    queue = os.environ.get("TEMPORAL_TASK_QUEUE", "agentzero-governance")

    try:
        from python.governance_runtime.temporal_workflow import GovernedRunInput, GovernedRunWorkflow

        client = await _get_client()
        await client.start_workflow(
            GovernedRunWorkflow.run,
            GovernedRunInput(run_id=run_id, context_id=context_id, project_name=project_name),
            id=run_id,
            task_queue=queue,
        )
        return {
            "run_id": run_id,
            "status": "queued",
            "persisted": True,
            "temporal": True,
        }
    except Exception:
        return _db_fallback_start(context_id=context_id, project_name=project_name)


async def signal_governed_run(
    *, run_id: str, signal: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    sig = str(signal or "").strip().lower()
    if sig not in {"pause", "resume", "cancel"}:
        raise ValueError(f"unsupported signal: {signal}")

    try:
        from python.governance_runtime.temporal_workflow import GovernedRunWorkflow

        client = await _get_client()
        handle = client.get_workflow_handle(run_id)
        if sig == "pause":
            await handle.signal(GovernedRunWorkflow.pause, payload or {})
        elif sig == "resume":
            await handle.signal(GovernedRunWorkflow.resume, payload or {})
        else:
            await handle.signal(GovernedRunWorkflow.cancel, payload or {})
        return {
            "run_id": run_id,
            "signal": sig,
            "status": _RUN_STATUS_BY_SIGNAL[sig],
            "persisted": True,
            "temporal": True,
        }
    except Exception:
        return _db_fallback_signal(run_id=run_id, signal=sig, payload=payload)
