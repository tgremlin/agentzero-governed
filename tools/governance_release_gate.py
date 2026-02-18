#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    file_path = pathlib.Path(path)
    if not file_path.exists():
        return {}
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric(report: dict[str, Any], key: str) -> float:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    value = metrics.get(key, 0.0)
    try:
        return float(value)
    except Exception:
        return 0.0


def evaluate_release_gate(
    eval_report: dict[str, Any],
    baseline_report: dict[str, Any] | None,
    *,
    min_tool_contract_pass_delta: float,
    max_policy_violation_delta: float,
    min_json_tool_call_validity_delta: float,
    max_approval_reject_delta: float,
) -> dict[str, Any]:
    baseline_report = baseline_report or {}
    current_ok = bool(eval_report.get("ok", False))
    current_gates = eval_report.get("gates") if isinstance(eval_report.get("gates"), dict) else {}
    hard_fail = not current_ok or not all(bool(v) for v in current_gates.values())

    regressions: dict[str, float] = {}
    if baseline_report:
        regressions = {
            "tool_contract_pass_rate_delta": _metric(eval_report, "tool_contract_pass_rate")
            - _metric(baseline_report, "tool_contract_pass_rate"),
            "policy_violation_rate_delta": _metric(eval_report, "policy_violation_rate")
            - _metric(baseline_report, "policy_violation_rate"),
            "json_tool_call_validity_delta": _metric(eval_report, "json_tool_call_validity")
            - _metric(baseline_report, "json_tool_call_validity"),
            "approval_reject_rate_delta": _metric(eval_report, "approval_reject_rate")
            - _metric(baseline_report, "approval_reject_rate"),
        }

    soft_fail = False
    if regressions:
        soft_fail = any(
            [
                regressions["tool_contract_pass_rate_delta"] < float(min_tool_contract_pass_delta),
                regressions["policy_violation_rate_delta"] > float(max_policy_violation_delta),
                regressions["json_tool_call_validity_delta"] < float(min_json_tool_call_validity_delta),
                regressions["approval_reject_rate_delta"] > float(max_approval_reject_delta),
            ]
        )

    if hard_fail:
        decision = "rollback"
    elif soft_fail:
        decision = "canary"
    else:
        decision = "promote"

    return {
        "ok": True,
        "decision": decision,
        "current_ok": current_ok,
        "hard_fail": hard_fail,
        "soft_fail": soft_fail,
        "regressions": regressions,
        "tolerances": {
            "min_tool_contract_pass_delta": float(min_tool_contract_pass_delta),
            "max_policy_violation_delta": float(max_policy_violation_delta),
            "min_json_tool_call_validity_delta": float(min_json_tool_call_validity_delta),
            "max_approval_reject_delta": float(max_approval_reject_delta),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic promotion gate for governed adapters (promote/canary/rollback)."
    )
    parser.add_argument("--eval-report", required=True, help="Path to current eval JSON report.")
    parser.add_argument("--baseline-report", default="", help="Optional baseline eval JSON report.")
    parser.add_argument("--output", default="", help="Optional output JSON file.")
    parser.add_argument("--min-tool-contract-pass-delta", type=float, default=-0.01)
    parser.add_argument("--max-policy-violation-delta", type=float, default=0.01)
    parser.add_argument("--min-json-tool-call-validity-delta", type=float, default=-0.02)
    parser.add_argument("--max-approval-reject-delta", type=float, default=0.02)
    args = parser.parse_args()

    eval_report = _load_json(args.eval_report)
    baseline_report = _load_json(args.baseline_report)
    result = evaluate_release_gate(
        eval_report,
        baseline_report,
        min_tool_contract_pass_delta=float(args.min_tool_contract_pass_delta),
        max_policy_violation_delta=float(args.max_policy_violation_delta),
        min_json_tool_call_validity_delta=float(args.min_json_tool_call_validity_delta),
        max_approval_reject_delta=float(args.max_approval_reject_delta),
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
