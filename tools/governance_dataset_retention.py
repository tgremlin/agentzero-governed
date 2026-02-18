#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _is_dataset_artifact(path: pathlib.Path) -> bool:
    name = path.name.lower()
    if name.endswith(".jsonl"):
        return True
    if name.endswith(".manifest.json"):
        return True
    return False


def apply_retention(
    datasets_dir: pathlib.Path,
    *,
    max_age_days: int,
    dry_run: bool,
) -> dict[str, Any]:
    cutoff = _utc_now() - dt.timedelta(days=max(0, int(max_age_days)))
    deleted: list[str] = []
    retained: list[str] = []
    checked = 0

    if not datasets_dir.exists():
        return {
            "ok": True,
            "datasets_dir": str(datasets_dir),
            "max_age_days": max_age_days,
            "dry_run": dry_run,
            "cutoff": cutoff.isoformat(),
            "checked": 0,
            "deleted": [],
            "retained": [],
        }

    for path in sorted(datasets_dir.glob("**/*")):
        if not path.is_file():
            continue
        if not _is_dataset_artifact(path):
            continue
        checked += 1
        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        rel = str(path.relative_to(datasets_dir))
        if modified < cutoff:
            deleted.append(rel)
            if not dry_run:
                path.unlink(missing_ok=True)
        else:
            retained.append(rel)

    return {
        "ok": True,
        "datasets_dir": str(datasets_dir),
        "max_age_days": max_age_days,
        "dry_run": dry_run,
        "cutoff": cutoff.isoformat(),
        "checked": checked,
        "deleted": deleted,
        "retained": retained,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply retention policy to governed dataset artifacts (JSONL + manifests)."
    )
    parser.add_argument(
        "--datasets-dir",
        default="/a0/usr/governance/datasets",
        help="Dataset artifacts directory.",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Delete files older than this many days.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report deletions without modifying files.",
    )
    args = parser.parse_args()

    result = apply_retention(
        pathlib.Path(args.datasets_dir),
        max_age_days=max(0, int(args.max_age_days)),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
