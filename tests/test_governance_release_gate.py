import json
import sys

import tools.governance_release_gate as gate_mod
from tools.governance_release_gate import evaluate_release_gate


def _report(*, ok: bool, tool: float, policy: float, json_valid: float, approval_reject: float) -> dict:
    return {
        "ok": ok,
        "gates": {
            "tool_contract_pass_rate": ok,
            "policy_violation_rate": ok,
            "json_tool_call_validity": ok,
            "approval_reject_rate": ok,
        },
        "metrics": {
            "tool_contract_pass_rate": tool,
            "policy_violation_rate": policy,
            "json_tool_call_validity": json_valid,
            "approval_reject_rate": approval_reject,
        },
    }


def test_release_gate_promote_when_all_good():
    current = _report(ok=True, tool=0.99, policy=0.02, json_valid=0.95, approval_reject=0.08)
    baseline = _report(ok=True, tool=0.98, policy=0.02, json_valid=0.94, approval_reject=0.09)
    out = evaluate_release_gate(
        current,
        baseline,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    assert out["decision"] == "promote"
    assert out["hard_fail"] is False
    assert out["soft_fail"] is False


def test_release_gate_canary_on_soft_regression():
    current = _report(ok=True, tool=0.97, policy=0.03, json_valid=0.91, approval_reject=0.12)
    baseline = _report(ok=True, tool=0.99, policy=0.02, json_valid=0.95, approval_reject=0.09)
    out = evaluate_release_gate(
        current,
        baseline,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    assert out["decision"] == "canary"
    assert out["hard_fail"] is False
    assert out["soft_fail"] is True


def test_release_gate_rollback_on_hard_failure():
    current = _report(ok=False, tool=0.70, policy=0.30, json_valid=0.60, approval_reject=0.40)
    out = evaluate_release_gate(
        current,
        baseline_report=None,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    assert out["decision"] == "rollback"
    assert out["hard_fail"] is True


def test_release_gate_rollback_when_required_gates_missing():
    current = {
        "ok": True,
        "gates": {},
        "metrics": {
            "tool_contract_pass_rate": 0.99,
            "policy_violation_rate": 0.01,
            "json_tool_call_validity": 0.95,
            "approval_reject_rate": 0.05,
        },
    }
    out = evaluate_release_gate(
        current,
        baseline_report=None,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    assert out["decision"] == "rollback"
    assert out["hard_fail"] is True
    assert any(err.startswith("missing_gate_keys:") for err in out["validation_errors"])


def test_release_gate_rollback_when_required_gate_values_are_not_bool():
    current = {
        "ok": True,
        "gates": {
            "tool_contract_pass_rate": "true",
            "policy_violation_rate": True,
            "json_tool_call_validity": True,
            "approval_reject_rate": True,
        },
        "metrics": {
            "tool_contract_pass_rate": 0.99,
            "policy_violation_rate": 0.01,
            "json_tool_call_validity": 0.95,
            "approval_reject_rate": 0.05,
        },
    }
    out = evaluate_release_gate(
        current,
        baseline_report=None,
        min_tool_contract_pass_delta=-0.01,
        max_policy_violation_delta=0.01,
        min_json_tool_call_validity_delta=-0.02,
        max_approval_reject_delta=0.02,
    )
    assert out["decision"] == "rollback"
    assert out["hard_fail"] is True
    assert "invalid_gate_values:tool_contract_pass_rate" in out["validation_errors"]


def test_release_gate_cli_emits_lifecycle_event(tmp_path, monkeypatch):
    eval_report = tmp_path / "eval.json"
    eval_report.write_text(
        json.dumps(
            {
                "ok": True,
                "gates": {
                    "tool_contract_pass_rate": True,
                    "policy_violation_rate": True,
                    "json_tool_call_validity": True,
                    "approval_reject_rate": True,
                },
                "metrics": {
                    "tool_contract_pass_rate": 0.99,
                    "policy_violation_rate": 0.01,
                    "json_tool_call_validity": 0.95,
                    "approval_reject_rate": 0.05,
                },
            }
        ),
        encoding="utf-8",
    )
    lifecycle = tmp_path / "training-lifecycle.jsonl"
    out_file = tmp_path / "release.json"

    monkeypatch.setenv("A0_GOV_TRAINING_EVENTS_FILE", str(lifecycle))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "governance_release_gate.py",
            "--eval-report",
            str(eval_report),
            "--output",
            str(out_file),
            "--lifecycle-project-name",
            "p1",
            "--lifecycle-run-id",
            "release-run-1",
        ],
    )
    rc = gate_mod.main()
    assert rc == 0
    rows = [json.loads(line) for line in lifecycle.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["event_type"] == "training.promotion.decision"
    assert rows[-1]["status"] == "promote"
