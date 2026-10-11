"""Audit records name the algorithm and key ID that signed them."""

from fortress_unified import ImmutableAuditLedger

KEY = "a-sufficiently-long-audit-key-for-tests"


def test_records_carry_algorithm_and_key_id():
    ledger = ImmutableAuditLedger(audit_key=KEY, key_id="test-key")
    ledger.append("commit", {"n": 1}, state={"n": 1})
    record = ledger.ledger[0]
    assert record["algorithm"] == "hmac-sha256"
    assert record["key_id"] == ledger.key_id
    assert KEY not in record["key_id"]
    assert record["key_id"] == "test-key"
    assert ledger.verify_integrity()


def test_a_configured_key_without_a_name_is_refused():
    import pytest

    with pytest.raises(ValueError, match="caller-named key ID"):
        ImmutableAuditLedger(audit_key=KEY)


def test_record_naming_another_key_fails_verification():
    ledger = ImmutableAuditLedger(audit_key=KEY, key_id="test-key")
    ledger.append("commit", {"n": 1}, state={"n": 1})
    ledger.ledger[0]["key_id"] = "forged"
    assert not ledger.verify_integrity()
