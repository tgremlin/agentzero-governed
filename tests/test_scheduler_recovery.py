import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from python.helpers.task_scheduler import TaskScheduler, TaskState


def _bare_scheduler() -> TaskScheduler:
    scheduler = object.__new__(TaskScheduler)
    scheduler._running_tasks_lock = threading.RLock()  # type: ignore[attr-defined]
    scheduler._running_deferred_tasks = {}  # type: ignore[attr-defined]
    return scheduler


def test_is_stale_running_task_true_when_old_running_without_handle():
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        uuid="t1",
        state=TaskState.RUNNING,
        updated_at=now - timedelta(minutes=20),
    )
    assert (
        TaskScheduler._is_stale_running_task(
            task=task,
            now=now,
            stale_after_seconds=300,
            has_local_handle=False,
        )
        is True
    )


def test_is_stale_running_task_false_with_local_handle_or_non_running():
    now = datetime.now(timezone.utc)
    running_task = SimpleNamespace(
        uuid="t1",
        state=TaskState.RUNNING,
        updated_at=now - timedelta(minutes=20),
    )
    idle_task = SimpleNamespace(
        uuid="t2",
        state=TaskState.IDLE,
        updated_at=now - timedelta(minutes=20),
    )

    assert (
        TaskScheduler._is_stale_running_task(
            task=running_task,
            now=now,
            stale_after_seconds=300,
            has_local_handle=True,
        )
        is False
    )
    assert (
        TaskScheduler._is_stale_running_task(
            task=idle_task,
            now=now,
            stale_after_seconds=300,
            has_local_handle=False,
        )
        is False
    )


def test_cancel_task_by_uuid_force_cancels_stale_running_task():
    scheduler = _bare_scheduler()
    task = SimpleNamespace(
        uuid="run_1",
        name="stale-task",
        state=TaskState.RUNNING,
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    updates: list[dict] = []
    saves: list[bool] = []

    async def _reload():
        return None

    def _get_task_by_uuid(task_uuid: str):
        return task if task_uuid == "run_1" else None

    def _cancel_running_task(_task_uuid: str, terminate_thread: bool = False):
        return False

    async def _update_task(task_uuid: str, **kwargs):
        updates.append({"task_uuid": task_uuid, **kwargs})
        task.state = kwargs.get("state", task.state)
        return task

    async def _save():
        saves.append(True)
        return None

    scheduler.reload = _reload  # type: ignore[method-assign]
    scheduler.get_task_by_uuid = _get_task_by_uuid  # type: ignore[method-assign]
    scheduler.cancel_running_task = _cancel_running_task  # type: ignore[method-assign]
    scheduler.update_task = _update_task  # type: ignore[method-assign]
    scheduler.save = _save  # type: ignore[method-assign]

    ok, status = asyncio.run(scheduler.cancel_task_by_uuid("run_1"))
    assert ok is True
    assert status == "cancelled_stale"
    assert updates
    assert updates[-1]["state"] == TaskState.IDLE
    assert saves


def test_recover_stale_running_tasks_resets_only_stale_without_handle(monkeypatch):
    scheduler = _bare_scheduler()
    now = datetime.now(timezone.utc)
    stale_task = SimpleNamespace(
        uuid="stale_1",
        name="stale",
        state=TaskState.RUNNING,
        updated_at=now - timedelta(minutes=20),
    )
    active_task = SimpleNamespace(
        uuid="active_1",
        name="active",
        state=TaskState.RUNNING,
        updated_at=now - timedelta(minutes=20),
    )
    updates: list[dict] = []
    saves: list[bool] = []

    async def _reload():
        return None

    def _get_tasks():
        return [stale_task, active_task]

    async def _update_task(task_uuid: str, **kwargs):
        updates.append({"task_uuid": task_uuid, **kwargs})
        return None

    async def _save():
        saves.append(True)
        return None

    monkeypatch.setenv("SCHEDULER_STALE_RUNNING_SECONDS", "300")
    scheduler.reload = _reload  # type: ignore[method-assign]
    scheduler.get_tasks = _get_tasks  # type: ignore[method-assign]
    scheduler.update_task = _update_task  # type: ignore[method-assign]
    scheduler.save = _save  # type: ignore[method-assign]
    scheduler._running_deferred_tasks = {"active_1": object()}  # type: ignore[attr-defined]

    recovered = asyncio.run(scheduler.recover_stale_running_tasks())
    assert recovered == ["stale_1"]
    assert len(updates) == 1
    assert updates[0]["task_uuid"] == "stale_1"
    assert updates[0]["state"] == TaskState.IDLE
    assert saves
