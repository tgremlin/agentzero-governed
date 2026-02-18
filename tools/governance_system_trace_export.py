#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

from python.helpers.system_trace_store import load_system_trace_items, load_system_trace_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export governed system trace items and deterministic summary.")
    parser.add_argument("--project-name", default="", help="Optional project filter.")
    parser.add_argument("--type", default="", help="Optional trace type filter.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", default="", help="Optional output path for JSON payload.")
    args = parser.parse_args()

    limit = max(1, min(int(args.limit), 5000))
    offset = max(0, int(args.offset))
    project_name = str(args.project_name or "").strip()
    type_filter = str(args.type or "").strip().lower()

    items = load_system_trace_items(type_filter=type_filter, project_name=project_name)
    total = len(items)
    page = items[offset : offset + limit]
    payload = {
        "ok": True,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "project_name": project_name or None,
        "type_filter": type_filter or None,
        "count": len(page),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": page,
        "summary": load_system_trace_summary(project_name=project_name),
    }

    output = str(args.output or "").strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
