#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from python.helpers.governance_training_lifecycle import append_training_lifecycle_event

REQUIRED_GATES = (
    "tool_contract_pass_rate",
    "policy_violation_rate",
    "json_tool_call_validity",
    "approval_reject_rate",
)

DEFAULT_MIN_TOOL_CONTRACT_PASS_DELTA = -0.01
DEFAULT_MAX_POLICY_VIOLATION_DELTA = 0.01
DEFAULT_MIN_JSON_TOOL_CALL_VALIDITY_DELTA = -0.02
DEFAULT_MAX_APPROVAL_REJECT_DELTA = 0.02


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


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _load_thresholds(path: str | None) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return {}
    thresholds = payload.get("release_gate_thresholds")
    if isinstance(thresholds, dict):
        return thresholds
    return payload


def _resolve_threshold_value(cli_value: Any, file_value: Any, default: float) -> float:
    if cli_value is not None:
        return _to_float(cli_value, default)
    if file_value is not None:
        return _to_float(file_value, default)
    return float(default)


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
    validation_errors: list[str] = []
    missing_gate_keys = [key for key in REQUIRED_GATES if key not in current_gates]
    if missing_gate_keys:
        validation_errors.append(f"missing_gate_keys:{','.join(missing_gate_keys)}")

    invalid_gate_keys = [key for key in REQUIRED_GATES if key in current_gates and not isinstance(current_gates.get(key), bool)]
    if invalid_gate_keys:
        validation_errors.append(f"invalid_gate_values:{','.join(invalid_gate_keys)}")

    gate_values = [bool(current_gates.get(key, False)) for key in REQUIRED_GATES]
    hard_fail = (not current_ok) or bool(validation_errors) or (not all(gate_values))

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
        "validation_errors": validation_errors,
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
    parser.add_argument(
        "--thresholds-file",
        default="conf/governance_release_gate_thresholds.json",
        help="Optional JSON file with release gate tolerance values.",
    )
    parser.add_argument("--min-tool-contract-pass-delta", type=float, default=None)
    parser.add_argument("--max-policy-violation-delta", type=float, default=None)
    parser.add_argument("--min-json-tool-call-validity-delta", type=float, default=None)
    parser.add_argument("--max-approval-reject-delta", type=float, default=None)
    parser.add_argument("--lifecycle-project-name", default="", help="Optional project name for lifecycle event.")
    parser.add_argument("--lifecycle-run-id", default="", help="Optional run ID for lifecycle event.")
    args = parser.parse_args()

    eval_report = _load_json(args.eval_report)
    baseline_report = _load_json(args.baseline_report)
    thresholds_file = str(args.thresholds_file).strip()
    threshold_map = _load_thresholds(thresholds_file)
    min_tool_contract_pass_delta = _resolve_threshold_value(
        args.min_tool_contract_pass_delta,
        threshold_map.get("min_tool_contract_pass_delta"),
        DEFAULT_MIN_TOOL_CONTRACT_PASS_DELTA,
    )
    max_policy_violation_delta = _resolve_threshold_value(
        args.max_policy_violation_delta,
        threshold_map.get("max_policy_violation_delta"),
        DEFAULT_MAX_POLICY_VIOLATION_DELTA,
    )
    min_json_tool_call_validity_delta = _resolve_threshold_value(
        args.min_json_tool_call_validity_delta,
        threshold_map.get("min_json_tool_call_validity_delta"),
        DEFAULT_MIN_JSON_TOOL_CALL_VALIDITY_DELTA,
    )
    max_approval_reject_delta = _resolve_threshold_value(
        args.max_approval_reject_delta,
        threshold_map.get("max_approval_reject_delta"),
        DEFAULT_MAX_APPROVAL_REJECT_DELTA,
    )
    result = evaluate_release_gate(
        eval_report,
        baseline_report,
        min_tool_contract_pass_delta=min_tool_contract_pass_delta,
        max_policy_violation_delta=max_policy_violation_delta,
        min_json_tool_call_validity_delta=min_json_tool_call_validity_delta,
        max_approval_reject_delta=max_approval_reject_delta,
    )
    result["threshold_source"] = (
        str(pathlib.Path(thresholds_file))
        if threshold_map
        else "defaults"
    )

    output = str(args.output).strip()
    if output:
        path = pathlib.Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    lifecycle_project = str(args.lifecycle_project_name).strip()
    if lifecycle_project:
        append_training_lifecycle_event(
            {
                "event_type": "training.promotion.decision",
                "project_name": lifecycle_project,
                "run_id": str(args.lifecycle_run_id).strip() or "release-gate",
                "stage": "promotion",
                "status": str(result.get("decision", "unknown")).strip().lower(),
                "details": {
                    "hard_fail": bool(result.get("hard_fail")),
                    "soft_fail": bool(result.get("soft_fail")),
                    "regressions": result.get("regressions", {}),
                },
            }
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
