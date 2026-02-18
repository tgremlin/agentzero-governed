from python.helpers.governance_eval_metrics import evaluate_records, evaluate_with_thresholds


def test_evaluate_records_computes_expected_metrics():
    records = [
        {
            "labels": {"train_eligible": True, "gold": True},
            "events": [
                {"type": "tool.contract.validation", "passed": True},
                {"type": "policy.check.decision", "decision": "allow"},
                {"type": "approval.resolved", "status": "approved"},
                {"type": "llm.response.parsed"},
            ],
        },
        {
            "labels": {"train_eligible": False, "gold": False},
            "events": [
                {"type": "tool.contract.validation", "passed": False},
                {"type": "policy.check.decision", "decision": "deny"},
                {"type": "approval.resolved", "status": "denied"},
                {"type": "llm.parse_failed"},
                {"type": "gate.retry.scheduled"},
            ],
        },
    ]
    out = evaluate_records(records)
    assert out["total_episodes"] == 2
    assert out["train_eligible_yield"] == 0.5
    assert out["gold_yield"] == 0.5
    assert out["tool_contract_pass_rate"] == 0.5
    assert out["policy_violation_rate"] == 0.5
    assert out["approval_reject_rate"] == 0.5
    assert out["json_tool_call_validity"] == 0.5
    assert out["mean_retry_count"] == 0.5


def test_evaluate_with_thresholds_flags_regressions():
    metrics = {
        "tool_contract_pass_rate": 0.90,
        "policy_violation_rate": 0.10,
        "json_tool_call_validity": 0.80,
        "approval_reject_rate": 0.30,
    }
    out = evaluate_with_thresholds(
        metrics,
        min_tool_contract_pass_rate=0.95,
        max_policy_violation_rate=0.05,
        min_json_tool_call_validity=0.90,
        max_approval_reject_rate=0.20,
    )
    assert out["ok"] is False
    assert out["gates"]["tool_contract_pass_rate"] is False
    assert out["gates"]["policy_violation_rate"] is False
    assert out["gates"]["json_tool_call_validity"] is False
    assert out["gates"]["approval_reject_rate"] is False
