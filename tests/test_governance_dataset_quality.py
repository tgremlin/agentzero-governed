from python.helpers.governance_dataset_quality import score_episode


def test_score_episode_gold_path():
    events = [
        {"type": "run.started"},
        {"type": "approval.resolved", "status": "approved"},
        {"type": "run.outcome", "outcome": "success"},
    ]
    out = score_episode(events)
    assert out["quality_score"] >= 0.85
    assert out["train_eligible"] is True
    assert out["gold"] is True
    assert out["tier"] == "gold"


def test_score_episode_penalizes_parse_failures_and_denies():
    events = [
        {"type": "policy.check.decision", "decision": "deny"},
        {"type": "llm.response.parse_failed"},
        {"type": "approval.resolved", "status": "denied"},
        {"type": "run.outcome", "outcome": "failure"},
    ]
    out = score_episode(events)
    assert out["quality_score"] < 0.65
    assert out["train_eligible"] is False
    assert out["gold"] is False
    assert out["tier"] in {"tier1", "audit_only"}
