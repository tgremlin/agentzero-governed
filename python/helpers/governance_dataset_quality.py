from __future__ import annotations

from typing import Any


def score_episode(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_types = [str(event.get("type", "")).strip().lower() for event in events]
    has_success_outcome = any(
        event_type == "run.outcome" and str(event.get("outcome", "")).strip().lower() == "success"
        for event_type, event in zip(event_types, events)
    )
    has_approved = any(
        event_type == "approval.resolved" and str(event.get("status", "")).strip().lower() == "approved"
        for event_type, event in zip(event_types, events)
    )
    has_denied = any(
        event_type == "approval.resolved" and str(event.get("status", "")).strip().lower() in {"denied", "reject", "rejected"}
        for event_type, event in zip(event_types, events)
    )
    parse_failures = sum(1 for event_type in event_types if event_type == "llm.response.parse_failed")
    policy_denies = sum(
        1
        for event_type, event in zip(event_types, events)
        if event_type == "policy.check.decision" and str(event.get("decision", "")).strip().lower() == "deny"
    )

    score = 0.0
    if has_success_outcome:
        score += 0.45
    if has_approved:
        score += 0.35
    if not has_denied:
        score += 0.10
    score += max(0.0, 0.10 - 0.05 * float(parse_failures))
    score -= 0.10 * float(policy_denies)
    score = max(0.0, min(1.0, round(score, 6)))

    tier = "audit_only"
    train_eligible = score >= 0.65
    gold = score >= 0.85 and has_approved and has_success_outcome and parse_failures == 0 and policy_denies == 0
    if gold:
        tier = "gold"
    elif train_eligible:
        tier = "tier2"
    else:
        tier = "tier1"

    return {
        "quality_score": score,
        "train_eligible": train_eligible,
        "gold": gold,
        "tier": tier,
        "signals": {
            "has_success_outcome": has_success_outcome,
            "has_approved": has_approved,
            "has_denied": has_denied,
            "parse_failures": parse_failures,
            "policy_denies": policy_denies,
        },
    }

