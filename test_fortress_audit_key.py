"""
The audit key: where ImmutableAuditLedger gets it, what it does without one.

The key is chosen when a ledger is built, so these tests set and clear the
environment around each case instead of starting new interpreters.
"""

import contextlib
import copy
import hashlib
import hmac
import logging
import os
import unittest
from unittest import mock

from fortress_unified import FortressConfig, FortressUnified, ImmutableAuditLedger

OLD_PUBLISHED_KEY = "fortress-key"  # the string an earlier version used as its default
LOG_NAME = "FORTRESS"
NO_KEY_WARNING = "no audit key"


def clean_env(**extra):
    """The current environment without FORTRESS_AUDIT_KEY, plus any overrides."""
    env = {k: v for k, v in os.environ.items() if k != "FORTRESS_AUDIT_KEY"}
    env.update(extra)
    return mock.patch.dict(os.environ, env, clear=True)


@contextlib.contextmanager
def captured_logs():
    """Collect what the FORTRESS logger emits at WARNING or above (works on Python 3.9)."""
    records = []

    class Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger(LOG_NAME)
    handler = Collector(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


class TestKeySource(unittest.TestCase):
    def test_the_argument_is_used(self):
        with clean_env():
            ledger = ImmutableAuditLedger("argument-key")
        self.assertEqual(ledger.audit_key, b"argument-key")
        self.assertFalse(ledger.ephemeral_key)

    def test_the_environment_variable_is_used_when_there_is_no_argument(self):
        with clean_env(FORTRESS_AUDIT_KEY="environment-key"):
            ledger = ImmutableAuditLedger()
        self.assertEqual(ledger.audit_key, b"environment-key")
        self.assertFalse(ledger.ephemeral_key)

    def test_the_argument_wins_over_the_environment_variable(self):
        with clean_env(FORTRESS_AUDIT_KEY="environment-key"):
            ledger = ImmutableAuditLedger("argument-key")
        self.assertEqual(ledger.audit_key, b"argument-key")

    def test_no_key_gives_a_random_per_ledger_key_and_says_so(self):
        with clean_env():
            first, second = ImmutableAuditLedger(), ImmutableAuditLedger()
        for ledger in (first, second):
            self.assertTrue(ledger.ephemeral_key)
            self.assertEqual(len(ledger.audit_key), 32)
            self.assertNotEqual(ledger.audit_key, OLD_PUBLISHED_KEY.encode())
        self.assertNotEqual(first.audit_key, second.audit_key)

    def test_empty_values_count_as_unset(self):
        with clean_env(FORTRESS_AUDIT_KEY=""):
            from_empty_env = ImmutableAuditLedger()
            from_empty_argument = ImmutableAuditLedger("")
        for ledger in (from_empty_env, from_empty_argument):
            self.assertTrue(ledger.ephemeral_key)
            self.assertEqual(len(ledger.audit_key), 32)


class TestWarning(unittest.TestCase):
    def test_a_keyless_ledger_logs_one_warning(self):
        with clean_env(), captured_logs() as records:
            ImmutableAuditLedger()
        self.assertEqual(len(records), 1)
        self.assertIn(NO_KEY_WARNING, records[0].getMessage())
        self.assertIn("FORTRESS_AUDIT_KEY", records[0].getMessage())

    def test_a_key_from_the_environment_is_silent(self):
        with clean_env(FORTRESS_AUDIT_KEY="environment-key"), captured_logs() as records:
            ImmutableAuditLedger()
        self.assertEqual(records, [])

    def test_a_key_from_the_argument_is_silent(self):
        with clean_env(), captured_logs() as records:
            ImmutableAuditLedger("argument-key")
        self.assertEqual(records, [])


class TestSigning(unittest.TestCase):
    def filled(self, ledger):
        ledger.append("first", {"n": 1})
        ledger.append("second", {"n": 2})
        return ledger

    def test_a_keyless_ledger_still_catches_tampering_in_process(self):
        with clean_env():
            ledger = self.filled(ImmutableAuditLedger())
        self.assertTrue(ledger.verify_integrity())
        ledger.ledger[0]["data"]["n"] = 99
        self.assertFalse(ledger.verify_integrity())

    def test_records_signed_with_the_old_default_do_not_verify_on_a_keyless_ledger(self):
        old = self.filled(ImmutableAuditLedger(OLD_PUBLISHED_KEY))
        self.assertTrue(old.verify_integrity())
        with clean_env():
            keyless = ImmutableAuditLedger()
        keyless.ledger = copy.deepcopy(old.ledger)
        self.assertFalse(keyless.verify_integrity())

    def test_a_keyless_ledger_is_not_signed_with_the_old_default(self):
        with clean_env():
            ledger = self.filled(ImmutableAuditLedger())
        record = dict(ledger.ledger[0])
        signature = record.pop("hmac")
        forged = hmac.new(
            OLD_PUBLISHED_KEY.encode(), ImmutableAuditLedger._canonical_json(record), hashlib.sha256
        ).hexdigest()
        self.assertFalse(hmac.compare_digest(signature, forged))

    def test_a_shared_environment_key_lets_another_ledger_verify_the_records(self):
        with clean_env(FORTRESS_AUDIT_KEY="shared-secret"):
            writer = self.filled(ImmutableAuditLedger())
            reader = ImmutableAuditLedger()
        reader.ledger = copy.deepcopy(writer.ledger)
        self.assertTrue(reader.verify_integrity())

    def test_a_different_key_does_not_verify_the_records(self):
        writer = self.filled(ImmutableAuditLedger("writer-key"))
        reader = ImmutableAuditLedger("another-key")
        reader.ledger = copy.deepcopy(writer.ledger)
        self.assertFalse(reader.verify_integrity())


class TestKernel(unittest.TestCase):
    def test_the_kernel_builds_its_ledger_from_the_environment(self):
        with clean_env(FORTRESS_AUDIT_KEY="environment-key"):
            kernel = FortressUnified(FortressConfig())
        self.assertEqual(kernel.audit.audit_key, b"environment-key")
        self.assertFalse(kernel.audit.ephemeral_key)

    def test_a_keyless_kernel_has_an_ephemeral_ledger(self):
        with clean_env():
            kernel = FortressUnified(FortressConfig())
        self.assertTrue(kernel.audit.ephemeral_key)
        self.assertNotEqual(kernel.audit.audit_key, OLD_PUBLISHED_KEY.encode())


if __name__ == "__main__":
    unittest.main()
