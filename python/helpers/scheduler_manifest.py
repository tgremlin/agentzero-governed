from __future__ import annotations

from datetime import datetime
from typing import Any

from python.helpers.task_scheduler import (
    AdHocTask,
    PlannedTask,
    ScheduledTask,
    TaskPlan,
    TaskSchedule,
    TaskType,
    parse_datetime,
)


def normalize_manifest_entry(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Task entry must be an object")

    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("Task entry missing required field: name")

    task_type = str(raw.get("type", "")).strip().lower()
    if task_type not in {"scheduled", "adhoc", "planned"}:
        raise ValueError(f"Task '{name}' has invalid type: {task_type}")

    system_prompt = str(raw.get("system_prompt", "")).strip()
    prompt = str(raw.get("prompt", "")).strip()
    if not system_prompt:
        raise ValueError(f"Task '{name}' missing required field: system_prompt")
    if not prompt:
        raise ValueError(f"Task '{name}' missing required field: prompt")

    attachments = raw.get("attachments", [])
    if not isinstance(attachments, list):
        raise ValueError(f"Task '{name}' attachments must be a list")

    normalized: dict[str, Any] = {
        "uuid": str(raw.get("uuid", "")).strip(),
        "name": name,
        "type": task_type,
        "state": str(raw.get("state", "")).strip().lower(),
        "system_prompt": system_prompt,
        "prompt": prompt,
        "attachments": [str(a) for a in attachments],
        "project_name": raw.get("project_name"),
        "project_color": raw.get("project_color"),
        "context_id": str(raw.get("context_id", "")).strip() or None,
    }

    if task_type == "scheduled":
        sched = raw.get("schedule", {})
        if not isinstance(sched, dict):
            raise ValueError(f"Task '{name}' schedule must be an object")
        normalized["schedule"] = {
            "minute": str(sched.get("minute", "*")),
            "hour": str(sched.get("hour", "*")),
            "day": str(sched.get("day", "*")),
            "month": str(sched.get("month", "*")),
            "weekday": str(sched.get("weekday", "*")),
            "timezone": str(sched.get("timezone", "")).strip() or None,
        }
    elif task_type == "planned":
        plan = raw.get("plan", [])
        if not isinstance(plan, list):
            raise ValueError(f"Task '{name}' plan must be a list of datetimes")
        normalized["plan"] = [str(v) for v in plan]
    elif task_type == "adhoc":
        token = str(raw.get("token", "")).strip()
        normalized["token"] = token or None

    return normalized


def find_existing_task(
    existing_tasks: list[ScheduledTask | AdHocTask | PlannedTask],
    entry: dict[str, Any],
) -> ScheduledTask | AdHocTask | PlannedTask | None:
    task_uuid = str(entry.get("uuid", "")).strip()
    name = str(entry.get("name", "")).strip()
    if task_uuid:
        hit = next((t for t in existing_tasks if t.uuid == task_uuid), None)
        if hit:
            return hit
    return next((t for t in existing_tasks if t.name == name), None)


def build_task_for_create(entry: dict[str, Any]):
    task_type = str(entry["type"]).strip().lower()
    context_id = entry.get("context_id")
    kwargs = dict(
        name=entry["name"],
        system_prompt=entry["system_prompt"],
        prompt=entry["prompt"],
        attachments=entry.get("attachments", []),
        context_id=context_id,
        project_name=entry.get("project_name"),
        project_color=entry.get("project_color"),
    )

    if task_type == "scheduled":
        schedule_raw = entry["schedule"]
        schedule = TaskSchedule(
            minute=schedule_raw["minute"],
            hour=schedule_raw["hour"],
            day=schedule_raw["day"],
            month=schedule_raw["month"],
            weekday=schedule_raw["weekday"],
            timezone=schedule_raw.get("timezone") or TaskSchedule(minute="*", hour="*", day="*", month="*", weekday="*").timezone,
        )
        return ScheduledTask.create(schedule=schedule, **kwargs)

    if task_type == "planned":
        todo: list[datetime] = []
        for dt_raw in entry.get("plan", []):
            parsed = parse_datetime(dt_raw)
            if parsed is None:
                raise ValueError(f"Task '{entry['name']}' has invalid plan datetime: {dt_raw}")
            todo.append(parsed)
        return PlannedTask.create(plan=TaskPlan.create(todo=todo, in_progress=None, done=[]), **kwargs)

    if task_type == "adhoc":
        return AdHocTask.create(token=entry.get("token") or "seed_task_token", **kwargs)

    raise ValueError(f"Unsupported task type: {task_type}")


def build_update_params(entry: dict[str, Any], existing_type: TaskType) -> dict[str, Any]:
    entry_type = TaskType(str(entry["type"]).strip().lower())
    if existing_type != entry_type:
        raise ValueError(
            f"Type mismatch for task '{entry['name']}': existing={existing_type}, manifest={entry_type}"
        )

    params: dict[str, Any] = {
        "name": entry["name"],
        "system_prompt": entry["system_prompt"],
        "prompt": entry["prompt"],
        "attachments": entry.get("attachments", []),
        "project_name": entry.get("project_name"),
        "project_color": entry.get("project_color"),
    }
    if entry.get("context_id"):
        params["context_id"] = entry["context_id"]

    state = str(entry.get("state", "")).strip().lower()
    if state in {"idle", "running", "disabled", "error"}:
        params["state"] = state

    if existing_type == TaskType.SCHEDULED:
        sched = entry["schedule"]
        params["schedule"] = TaskSchedule(
            minute=sched["minute"],
            hour=sched["hour"],
            day=sched["day"],
            month=sched["month"],
            weekday=sched["weekday"],
            timezone=sched.get("timezone") or TaskSchedule(minute="*", hour="*", day="*", month="*", weekday="*").timezone,
        )
    elif existing_type == TaskType.PLANNED and "plan" in entry:
        todo: list[datetime] = []
        for dt_raw in entry.get("plan", []):
            parsed = parse_datetime(dt_raw)
            if parsed is None:
                raise ValueError(f"Task '{entry['name']}' has invalid plan datetime: {dt_raw}")
            todo.append(parsed)
        params["plan"] = TaskPlan.create(todo=todo, in_progress=None, done=[])
    elif existing_type == TaskType.AD_HOC and entry.get("token"):
        params["token"] = entry["token"]

    return params
