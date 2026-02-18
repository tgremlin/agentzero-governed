from python.governance_runtime.repos import _resolve_audit_sequence_number


def test_sequence_uses_explicit_when_greater_than_previous():
    assert _resolve_audit_sequence_number(prev_seq=2, candidate_sequence=5) == 5


def test_sequence_increments_when_explicit_repeats_or_regresses():
    assert _resolve_audit_sequence_number(prev_seq=3, candidate_sequence=3) == 4
    assert _resolve_audit_sequence_number(prev_seq=3, candidate_sequence=2) == 4


def test_sequence_increments_when_candidate_missing_or_invalid():
    assert _resolve_audit_sequence_number(prev_seq=7, candidate_sequence=None) == 8
    assert _resolve_audit_sequence_number(prev_seq=7, candidate_sequence="not-a-number") == 8
