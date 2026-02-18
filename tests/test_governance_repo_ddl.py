from python.governance_runtime.repos import _GOVERNANCE_DDL


def test_governance_audit_secret_payload_guard_present_in_ddl():
    assert "enforce_secret_payload_suppression" in _GOVERNANCE_DDL
    assert "trg_governance_audit_secret_payload_guard" in _GOVERNANCE_DDL
