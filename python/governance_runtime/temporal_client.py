from __future__ import annotations

import os
import uuid
from typing import Any

from python.governance_runtime.repos import get_postgres_repo


_RUN_STATUS_BY_SIGNAL = {
    "pause": "paused",
    "resume": "running",
    "cancel": "cancelled",
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def is_temporal_enabled() -> bool:
    return _env_flag("GOV_TEMPORAL_ENABLED", default=False)


def start_governed_run(*, context_id: str, project_name: str | None) -> dict[str, Any]:
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
    }


def signal_governed_run(*, run_id: str, signal: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
            persisted = True
        except Exception:
            persisted = False

    return {
        "run_id": run_id,
        "signal": sig,
        "status": status,
        "persisted": persisted,
    }
