#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any

from python.helpers.system_trace_store import load_system_trace_summary


def _parse_iso(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _age_hours(now: dt.datetime, value: Any) -> float | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600.0)


def evaluate_trace_health(
    summary: dict[str, Any],
    *,
    require_artifacts: bool,
    max_dataset_age_hours: int,
    max_lifecycle_age_hours: int,
    allow_active_runs: bool,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    now_ts = now or dt.datetime.now(dt.timezone.utc)
    checks: list[dict[str, Any]] = []

    sources = summary.get("sources") if isinstance(summary.get("sources"), dict) else {}
    dataset_summary = summary.get("dataset_summary") if isinstance(summary.get("dataset_summary"), dict) else {}
    lifecycle_summary = summary.get("lifecycle_summary") if isinstance(summary.get("lifecycle_summary"), dict) else {}

    dataset_count = int(sources.get("dataset_exports", 0) or 0)
    lifecycle_count = int(sources.get("training_lifecycle", 0) or 0)
    active_run_count = int(lifecycle_summary.get("active_run_count", 0) or 0)

    if require_artifacts:
        checks.append(
            {
                "name": "dataset_exports_present",
                "ok": dataset_count > 0,
                "details": {"count": dataset_count},
            }
        )
        checks.append(
            {
                "name": "training_lifecycle_present",
                "ok": lifecycle_count > 0,
                "details": {"count": lifecycle_count},
            }
        )

    dataset_age = _age_hours(now_ts, dataset_summary.get("latest_generated_at"))
    if dataset_age is None:
        checks.append(
            {
                "name": "dataset_freshness",
                "ok": not require_artifacts,
                "details": {"max_hours": int(max_dataset_age_hours), "actual_hours": None},
            }
        )
    else:
        checks.append(
            {
                "name": "dataset_freshness",
                "ok": dataset_age <= float(max_dataset_age_hours),
                "details": {"max_hours": int(max_dataset_age_hours), "actual_hours": round(dataset_age, 3)},
            }
        )

    lifecycle_age = _age_hours(now_ts, lifecycle_summary.get("latest_generated_at"))
    if lifecycle_age is None:
        checks.append(
            {
                "name": "lifecycle_freshness",
                "ok": not require_artifacts,
                "details": {"max_hours": int(max_lifecycle_age_hours), "actual_hours": None},
            }
        )
    else:
        checks.append(
            {
                "name": "lifecycle_freshness",
                "ok": lifecycle_age <= float(max_lifecycle_age_hours),
                "details": {"max_hours": int(max_lifecycle_age_hours), "actual_hours": round(lifecycle_age, 3)},
            }
        )

    checks.append(
        {
            "name": "active_run_count",
            "ok": allow_active_runs or active_run_count == 0,
            "details": {"allow_active_runs": bool(allow_active_runs), "active_run_count": active_run_count},
        }
    )

    return {
        "ok": all(bool(item.get("ok", False)) for item in checks),
        "generated_at": now_ts.isoformat().replace("+00:00", "Z"),
        "project_name": summary.get("project_name"),
        "checks": checks,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic health-check for governed tracing/training artifacts."
    )
    parser.add_argument("--project-name", default="", help="Optional project filter.")
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Fail if dataset exports and lifecycle events are missing.",
    )
    parser.add_argument(
        "--max-dataset-age-hours",
        type=int,
        default=168,
        help="Maximum allowed age in hours for latest dataset export.",
    )
    parser.add_argument(
        "--max-lifecycle-age-hours",
        type=int,
        default=168,
        help="Maximum allowed age in hours for latest training lifecycle event.",
    )
    parser.add_argument(
        "--allow-active-runs",
        action="store_true",
        help="Do not fail when lifecycle indicates active runs.",
    )
    parser.add_argument("--output", default="", help="Optional output JSON report path.")
    args = parser.parse_args()

    summary = load_system_trace_summary(project_name=str(args.project_name or "").strip())
    report = evaluate_trace_health(
        summary,
        require_artifacts=bool(args.require_artifacts),
        max_dataset_age_hours=max(0, int(args.max_dataset_age_hours)),
        max_lifecycle_age_hours=max(0, int(args.max_lifecycle_age_hours)),
        allow_active_runs=bool(args.allow_active_runs),
    )

    output = str(args.output or "").strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, sort_keys=True))
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
