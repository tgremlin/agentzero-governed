from __future__ import annotations

from typing import Any


def _safe_div(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return float(num) / float(den)


def evaluate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    train_eligible = 0
    gold = 0

    tool_contract_pass = 0
    tool_contract_total = 0
    policy_denies = 0
    policy_total = 0
    approvals_denied = 0
    approvals_total = 0
    parsed_ok = 0
    parsed_fail = 0
    retry_total = 0

    for record in records:
        labels = record.get("labels") if isinstance(record.get("labels"), dict) else {}
        quality = record.get("quality") if isinstance(record.get("quality"), dict) else {}
        if bool(labels.get("train_eligible", quality.get("train_eligible", False))):
            train_eligible += 1
        if bool(labels.get("gold", quality.get("gold", False))):
            gold += 1

        events = record.get("events") if isinstance(record.get("events"), list) else []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type", "")).strip().lower()
            if event_type == "tool.contract.validation":
                tool_contract_total += 1
                if bool(event.get("passed", False)):
                    tool_contract_pass += 1
            elif event_type == "policy.check.decision":
                policy_total += 1
                decision = str(event.get("decision", "")).strip().lower()
                if decision == "deny":
                    policy_denies += 1
            elif event_type == "approval.resolved":
                approvals_total += 1
                status = str(event.get("status", "")).strip().lower()
                if status in {"denied", "reject", "rejected"}:
                    approvals_denied += 1
            elif event_type == "llm.response.parsed":
                parsed_ok += 1
            elif event_type == "llm.parse_failed":
                parsed_fail += 1
            elif event_type == "gate.retry.scheduled":
                retry_total += 1

    parse_total = parsed_ok + parsed_fail
    return {
        "total_episodes": total,
        "train_eligible_count": train_eligible,
        "gold_count": gold,
        "train_eligible_yield": _safe_div(train_eligible, total),
        "gold_yield": _safe_div(gold, total),
        "tool_contract_pass_rate": _safe_div(tool_contract_pass, tool_contract_total),
        "policy_violation_rate": _safe_div(policy_denies, policy_total),
        "approval_reject_rate": _safe_div(approvals_denied, approvals_total),
        "json_tool_call_validity": _safe_div(parsed_ok, parse_total),
        "mean_retry_count": _safe_div(retry_total, total),
        "counters": {
            "tool_contract_pass": tool_contract_pass,
            "tool_contract_total": tool_contract_total,
            "policy_denies": policy_denies,
            "policy_total": policy_total,
            "approvals_denied": approvals_denied,
            "approvals_total": approvals_total,
            "parsed_ok": parsed_ok,
            "parsed_fail": parsed_fail,
            "retry_total": retry_total,
        },
    }


def evaluate_with_thresholds(
    metrics: dict[str, Any],
    *,
    min_tool_contract_pass_rate: float,
    max_policy_violation_rate: float,
    min_json_tool_call_validity: float,
    max_approval_reject_rate: float,
) -> dict[str, Any]:
    gates = {
        "tool_contract_pass_rate": float(metrics.get("tool_contract_pass_rate", 0.0))
        >= float(min_tool_contract_pass_rate),
        "policy_violation_rate": float(metrics.get("policy_violation_rate", 0.0))
        <= float(max_policy_violation_rate),
        "json_tool_call_validity": float(metrics.get("json_tool_call_validity", 0.0))
        >= float(min_json_tool_call_validity),
        "approval_reject_rate": float(metrics.get("approval_reject_rate", 0.0))
        <= float(max_approval_reject_rate),
    }
    return {
        "ok": all(gates.values()),
        "gates": gates,
        "thresholds": {
            "min_tool_contract_pass_rate": float(min_tool_contract_pass_rate),
            "max_policy_violation_rate": float(max_policy_violation_rate),
            "min_json_tool_call_validity": float(min_json_tool_call_validity),
            "max_approval_reject_rate": float(max_approval_reject_rate),
        },
        "metrics": metrics,
    }
