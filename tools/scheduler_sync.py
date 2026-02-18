#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from python.helpers.scheduler_manifest import (
    build_task_for_create,
    build_update_params,
    find_existing_task,
    normalize_manifest_entry,
)
from python.helpers.task_scheduler import TaskScheduler, serialize_task


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise RuntimeError("Manifest must contain 'tasks' list")
    return [normalize_manifest_entry(item) for item in tasks]


async def _export_manifest(path: Path) -> dict[str, Any]:
    scheduler = TaskScheduler.get()
    await scheduler.reload()
    raw_tasks = scheduler.serialize_all_tasks()
    exported: list[dict[str, Any]] = []
    for task in raw_tasks:
        entry = {
            "uuid": task.get("uuid"),
            "name": task.get("name"),
            "type": task.get("type"),
            "system_prompt": task.get("system_prompt"),
            "prompt": task.get("prompt"),
            "attachments": task.get("attachments", []),
            "project_name": task.get("project_name"),
            "project_color": task.get("project_color"),
            "context_id": task.get("context_id"),
        }
        if task.get("type") == "scheduled":
            entry["schedule"] = task.get("schedule", {})
        if task.get("type") == "planned":
            plan = task.get("plan", {})
            entry["plan"] = plan.get("todo", []) if isinstance(plan, dict) else []
        if task.get("type") == "adhoc":
            entry["token"] = task.get("token")
        exported.append(entry)
    out = {"tasks": exported}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return {"exported": len(exported), "path": str(path)}


async def _sync_manifest(path: Path, apply: bool) -> dict[str, Any]:
    entries = _load_manifest(path)
    scheduler = TaskScheduler.get()
    await scheduler.reload()
    existing = scheduler.get_tasks()

    actions: list[dict[str, Any]] = []
    for entry in entries:
        hit = find_existing_task(existing, entry)
        if hit is None:
            actions.append(
                {
                    "action": "create",
                    "name": entry["name"],
                    "type": entry["type"],
                    "uuid": entry.get("uuid", ""),
                }
            )
            if apply:
                task = build_task_for_create(entry)
                await scheduler.add_task(task)
                actions[-1]["created_uuid"] = task.uuid
            continue

        params = build_update_params(entry, hit.type)
        actions.append(
            {
                "action": "update",
                "name": hit.name,
                "uuid": hit.uuid,
                "type": str(hit.type),
            }
        )
        if apply:
            await scheduler.update_task(hit.uuid, **params)

    if apply:
        await scheduler.save()
        await scheduler.reload()

    return {
        "apply": apply,
        "manifest_path": str(path),
        "count": len(actions),
        "actions": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync scheduler tasks from a versioned manifest."
    )
    parser.add_argument(
        "--path",
        default="scheduler/tasks.seed.json",
        help="Path to scheduler manifest JSON (default: scheduler/tasks.seed.json)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, prints dry-run actions only.",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export current scheduler tasks to the manifest path and exit.",
    )
    args = parser.parse_args()
    path = Path(args.path)

    if args.export:
        result = asyncio.run(_export_manifest(path))
    else:
        result = asyncio.run(_sync_manifest(path, apply=bool(args.apply)))

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
