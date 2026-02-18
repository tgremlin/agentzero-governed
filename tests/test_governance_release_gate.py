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
