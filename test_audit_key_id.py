"""Audit records name the algorithm and key ID that signed them."""

from fortress_unified import ImmutableAuditLedger

KEY = "a-sufficiently-long-audit-key-for-tests"


def test_records_carry_algorithm_and_key_id():
    ledger = ImmutableAuditLedger(audit_key=KEY)
    ledger.append("commit", {"n": 1}, state={"n": 1})
    record = ledger.ledger[0]
    assert record["signature_algorithm"] == "hmac-sha256"
    assert record["key_id"] == ledger.key_id
    assert KEY not in record["key_id"]
    assert ledger.verify_integrity()


def test_key_id_is_stable_for_the_same_key():
    assert ImmutableAuditLedger(audit_key=KEY).key_id == ImmutableAuditLedger(audit_key=KEY).key_id


def test_record_naming_another_key_fails_verification():
    ledger = ImmutableAuditLedger(audit_key=KEY)
    ledger.append("commit", {"n": 1}, state={"n": 1})
    ledger.ledger[0]["key_id"] = "key-forged00000"
    assert not ledger.verify_integrity()
