#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(raw)
    except Exception:
        return None


def _load_manifests(root: pathlib.Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not root.exists():
        return manifests
    for path in sorted(root.glob("**/*.manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload["_path"] = str(path)
        manifests.append(payload)
    return manifests


def evaluate_training_trigger(
    manifests: list[dict[str, Any]],
    *,
    min_record_count: int,
    min_gold_count: int,
    max_manifest_age_days: int,
) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    max_age = max(0, int(max_manifest_age_days))
    cutoff = now - dt.timedelta(days=max_age)

    eligible: list[dict[str, Any]] = []
    for item in manifests:
        if str(item.get("purpose", "")).strip().lower() != "training":
            continue
        created_at = _parse_iso(item.get("generated_at"))
        if created_at is not None and created_at < cutoff:
            continue
        eligible.append(item)

    total_records = sum(int(item.get("record_count", 0) or 0) for item in eligible)
    total_gold = sum(int(item.get("gold_count", 0) or 0) for item in eligible)
    should_trigger = total_records >= min_record_count and total_gold >= min_gold_count

    return {
        "ok": True,
        "checked_manifests": len(manifests),
        "eligible_manifests": len(eligible),
        "total_records": total_records,
        "total_gold": total_gold,
        "min_record_count": min_record_count,
        "min_gold_count": min_gold_count,
        "max_manifest_age_days": max_age,
        "trigger_training": should_trigger,
        "manifests": [
            {
                "path": str(item.get("_path", "")),
                "generated_at": item.get("generated_at"),
                "record_count": int(item.get("record_count", 0) or 0),
                "gold_count": int(item.get("gold_count", 0) or 0),
                "sha256": item.get("sha256"),
            }
            for item in eligible
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate governed training dataset manifests and emit a deterministic training trigger decision."
    )
    parser.add_argument(
        "--datasets-dir",
        default="/a0/usr/governance/datasets",
        help="Directory containing dataset manifest files.",
    )
    parser.add_argument("--min-record-count", type=int, default=2000, help="Minimum records required to trigger.")
    parser.add_argument("--min-gold-count", type=int, default=200, help="Minimum gold records required to trigger.")
    parser.add_argument(
        "--max-manifest-age-days",
        type=int,
        default=14,
        help="Maximum age of manifest to consider (days).",
    )
    parser.add_argument("--output", default="", help="Optional output path for trigger plan JSON.")
    args = parser.parse_args()

    manifests = _load_manifests(pathlib.Path(args.datasets_dir))
    result = evaluate_training_trigger(
        manifests,
        min_record_count=max(0, int(args.min_record_count)),
        min_gold_count=max(0, int(args.min_gold_count)),
        max_manifest_age_days=max(0, int(args.max_manifest_age_days)),
    )
    output = str(args.output).strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
