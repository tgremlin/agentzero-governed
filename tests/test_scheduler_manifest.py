from datetime import timezone

import pytest

from python.helpers.scheduler_manifest import (
    build_update_params,
    find_existing_task,
    normalize_manifest_entry,
)
from python.helpers.task_scheduler import ScheduledTask, TaskSchedule


def test_normalize_manifest_entry_requires_name_and_type():
    with pytest.raises(ValueError):
        normalize_manifest_entry({"type": "scheduled"})
    with pytest.raises(ValueError):
        normalize_manifest_entry({"name": "x", "type": "invalid"})


def test_normalize_manifest_entry_scheduled_defaults():
    out = normalize_manifest_entry(
        {
            "name": "t1",
            "type": "scheduled",
            "system_prompt": "sys",
            "prompt": "prompt",
            "schedule": {"minute": "0", "hour": "1", "day": "*", "month": "*", "weekday": "*"},
        }
    )
    assert out["type"] == "scheduled"
    assert out["schedule"]["minute"] == "0"
    assert out["attachments"] == []


def test_find_existing_task_prefers_uuid_then_name():
    schedule = TaskSchedule(minute="0", hour="1", day="*", month="*", weekday="*")
    t1 = ScheduledTask.create(name="A", system_prompt="s", prompt="p", schedule=schedule)
    t2 = ScheduledTask.create(name="B", system_prompt="s", prompt="p", schedule=schedule)

    hit_uuid = find_existing_task([t1, t2], {"uuid": t2.uuid, "name": "A"})
    assert hit_uuid is t2
    hit_name = find_existing_task([t1, t2], {"uuid": "", "name": "A"})
    assert hit_name is t1


def test_build_update_params_for_scheduled():
    schedule = TaskSchedule(minute="0", hour="1", day="*", month="*", weekday="*")
    task = ScheduledTask.create(name="A", system_prompt="s", prompt="p", schedule=schedule)
    entry = normalize_manifest_entry(
        {
            "name": "A",
            "type": "scheduled",
            "system_prompt": "sys2",
            "prompt": "p2",
            "attachments": ["/tmp/x"],
            "schedule": {
                "minute": "5",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "*",
                "timezone": "UTC",
            },
        }
    )
    params = build_update_params(entry, task.type)
    assert params["name"] == "A"
    assert params["system_prompt"] == "sys2"
    assert params["attachments"] == ["/tmp/x"]
    assert params["schedule"].minute == "5"
    assert params["schedule"].timezone in {"UTC", "Etc/UTC"}
