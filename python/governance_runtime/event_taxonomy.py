from __future__ import annotations


EVENT_RUN_STARTED = "run.started"
EVENT_RUN_OUTCOME = "run.outcome"
EVENT_TOOL_CALL_REQUESTED = "tool.call.requested"
EVENT_POLICY_CHECK_DECISION = "policy.check.decision"
EVENT_APPROVAL_REQUESTED = "approval.requested"
EVENT_APPROVAL_RESOLVED = "approval.resolved"
EVENT_SECURITY_SECRET_SCAN_FAILED = "security.secret_scan_failed"

DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_REQUIRE_APPROVAL = "require_approval"
DECISION_TRANSFORM = "transform"
DECISION_REDACT = "redact"
DECISION_ROUTE = "route"
DECISION_QUARANTINE = "quarantine"

ALL_POLICY_DECISIONS = {
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_REQUIRE_APPROVAL,
    DECISION_TRANSFORM,
    DECISION_REDACT,
    DECISION_ROUTE,
    DECISION_QUARANTINE,
}
