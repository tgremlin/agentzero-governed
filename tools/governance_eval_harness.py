#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from python.helpers.governance_eval_metrics import evaluate_records, evaluate_with_thresholds


def _load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate governed dataset JSONL against deterministic release gates.")
    parser.add_argument("--dataset-jsonl", required=True, help="Path to governed episode dataset JSONL.")
    parser.add_argument("--output", default="", help="Optional output JSON report path.")
    parser.add_argument("--min-tool-contract-pass-rate", type=float, default=0.98)
    parser.add_argument("--max-policy-violation-rate", type=float, default=0.05)
    parser.add_argument("--min-json-tool-call-validity", type=float, default=0.90)
    parser.add_argument("--max-approval-reject-rate", type=float, default=0.20)
    args = parser.parse_args()

    records = _load_jsonl(pathlib.Path(args.dataset_jsonl))
    metrics = evaluate_records(records)
    report = evaluate_with_thresholds(
        metrics,
        min_tool_contract_pass_rate=float(args.min_tool_contract_pass_rate),
        max_policy_violation_rate=float(args.max_policy_violation_rate),
        min_json_tool_call_validity=float(args.min_json_tool_call_validity),
        max_approval_reject_rate=float(args.max_approval_reject_rate),
    )

    output = str(args.output).strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
