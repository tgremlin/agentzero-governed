#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from tools.governance_release_gate import evaluate_release_gate


def build_bad_eval_report() -> dict[str, Any]:
    return {
        "ok": False,
        "gates": {
            "tool_contract_pass_rate": False,
            "policy_violation_rate": False,
            "json_tool_call_validity": False,
            "approval_reject_rate": False,
        },
        "metrics": {
            "tool_contract_pass_rate": 0.0,
            "policy_violation_rate": 1.0,
            "json_tool_call_validity": 0.0,
            "approval_reject_rate": 1.0,
        },
    }


def run_rollback_drill(*, output_dir: pathlib.Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    eval_report = build_bad_eval_report()
    decision = evaluate_release_gate(
        eval_report,
        baseline_report=None,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    passed = str(decision.get("decision", "")).strip().lower() == "rollback"

    eval_path = output_dir / "phase3-drill.eval-report.json"
    decision_path = output_dir / "phase3-drill.release-gate.json"
    summary_path = output_dir / "phase3-drill.summary.json"
    eval_path.write_text(json.dumps(eval_report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    decision_path.write_text(json.dumps(decision, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary = {
        "ok": passed,
        "expected_decision": "rollback",
        "actual_decision": decision.get("decision"),
        "paths": {
            "eval_report": str(eval_path),
            "release_gate": str(decision_path),
        },
    }
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary["paths"]["summary"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic Phase 3 rollback drill (release gate must return rollback)."
    )
    parser.add_argument(
        "--output-dir",
        default="/a0/tmp/governance-phase3-drill",
        help="Directory where drill artifacts are written.",
    )
    args = parser.parse_args()

    result = run_rollback_drill(output_dir=pathlib.Path(str(args.output_dir)))
    print(json.dumps(result, sort_keys=True))
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
