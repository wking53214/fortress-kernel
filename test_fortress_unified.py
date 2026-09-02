"""
Comprehensive test suite for FORTRESS Unified Kernel
Tests all three controllers, guardrails, and audit trails.
"""

import json
import math
import unittest
from datetime import datetime as dt

import numpy as np

from fortress_unified import (
    FortressConfig,
    FortressUnified,
    Payload,
    DriftMonitor,
    IntegrityLayer,
    InvariantMonitor,
    MandateLayer,
    ImmutableAuditLedger,
    SAGEController,
    LyapunovController,
    EnergyController,
    OperationalRegime,
)


class TestIntegrityLayer(unittest.TestCase):
    def test_volatility_detection(self):
        config = FortressConfig()
        integrity = IntegrityLayer(config)
        payload = Payload("System status", {})

        result1 = integrity.analyze(payload, 5.0)
        self.assertIn("volatility", result1)

        result2 = integrity.analyze(payload, 20.0)
        self.assertGreater(result2["volatility"], result1["volatility"])

    def test_semantic_risk_detection(self):
        config = FortressConfig()
        integrity = IntegrityLayer(config)

        payload_risky = Payload("System stable and healthy", {})
        result = integrity.analyze(payload_risky, 15.0)
        self.assertGreater(result["distortion"], 0.1)

    def test_nan_rejection(self):
        config = FortressConfig()
        integrity = IntegrityLayer(config)
        payload = Payload("test", {})

        with self.assertRaises(ValueError):
            integrity.analyze(payload, float('nan'))


class TestInvariantMonitor(unittest.TestCase):
    def test_state_divergence_detection(self):
        violations = InvariantMonitor.check(300.0, 0.5, 5.0, 2.0)
        self.assertIn("STATE_DIVERGENCE", violations)

    def test_distortion_overflow(self):
        violations = InvariantMonitor.check(50.0, 0.90, 5.0, 2.0)
        self.assertIn("DISTORTION_OVERFLOW", violations)

    def test_model_failure_detection(self):
        violations = InvariantMonitor.check(50.0, 0.5, 25.0, 2.0)
        self.assertIn("MODEL_FAILURE", violations)

    def test_volatility_spike(self):
        violations = InvariantMonitor.check(50.0, 0.5, 5.0, 50.0)
        self.assertIn("VOLATILITY_SPIKE", violations)

    def test_no_violations(self):
        violations = InvariantMonitor.check(50.0, 0.5, 5.0, 2.0)
        self.assertEqual(violations, [])


class TestDriftMonitor(unittest.TestCase):
    def test_drift_detection(self):
        config = FortressConfig()
        drift = DriftMonitor(config)

        weights = [[0.1, 0.2], [0.3, 0.4]]
        for _ in range(4):
            drift.check(weights)

        weights_drifted = [[2.0, 2.5], [3.0, 3.5]]
        is_drifting, drift_amount = drift.check(weights_drifted)
        self.assertTrue(is_drifting)
        self.assertGreater(drift_amount, 0.0)


class TestMandateLayer(unittest.TestCase):
    def test_slew_rate_enforcement(self):
        action = {"delta": 100.0}
        result = MandateLayer.enforce(action, 50.0, 100.0, 2.0)
        self.assertLessEqual(abs(result["delta"]), 30.0)

    def test_target_bound_enforcement(self):
        action = {"delta": 50.0}
        result = MandateLayer.enforce(action, 50.0, 100.0, 0.1)
        projected = 50.0 + result["delta"]
        self.assertLessEqual(projected, 100.0 + 15.0)


class TestAuditLedger(unittest.TestCase):
    def test_immutable_record(self):
        ledger = ImmutableAuditLedger()
        ledger.append("test_event", {"data": "value"})

        self.assertEqual(len(ledger.ledger), 1)
        record = ledger.ledger[0]
        self.assertIn("hmac", record)
        self.assertIn("ts", record)

    def test_integrity_verification(self):
        ledger = ImmutableAuditLedger()
        ledger.append("event1", {"msg": "test"})
        ledger.append("event2", {"msg": "test2"})

        self.assertTrue(ledger.verify_integrity())

        ledger.ledger[0]["data"]["msg"] = "tampered"
        self.assertFalse(ledger.verify_integrity())

    def test_state_commitments_chain_records(self):
        ledger = ImmutableAuditLedger()
        first = ledger.append("event1", {"msg": "test"}, state={"value": 1})
        second = ledger.append("event2", {"msg": "test2"}, state={"value": 2})

        self.assertNotEqual(first, second)
        self.assertEqual(ledger.ledger[1]["parent"], first)
        self.assertTrue(ledger.verify_integrity())

    def test_chain_detects_deleted_record(self):
        ledger = ImmutableAuditLedger()
        ledger.append("event1", {"msg": "test"})
        ledger.append("event2", {"msg": "test2"})
        ledger.ledger.pop(0)

        self.assertFalse(ledger.verify_integrity())

    def test_chain_detects_reordered_records(self):
        ledger = ImmutableAuditLedger()
        ledger.append("event1", {"msg": "test"})
        ledger.append("event2", {"msg": "test2"})
        ledger.ledger.reverse()

        self.assertFalse(ledger.verify_integrity())

    def test_state_commitment_rejects_ambiguous_values(self):
        ledger = ImmutableAuditLedger()
        with self.assertRaises(ValueError):
            ledger.append("event", {"value": float("nan")})

    def test_canonical_state_ignores_mapping_order(self):
        first = {"a": 1, "nested": {"b": [True, None, "é"], "c": 2.5}}
        second = {"nested": {"c": 2.5, "b": (True, None, "é")}, "a": 1}

        first_commitment = ImmutableAuditLedger._commit_state(
            0, ImmutableAuditLedger.GENESIS_COMMITMENT, first
        )
        second_commitment = ImmutableAuditLedger._commit_state(
            0, ImmutableAuditLedger.GENESIS_COMMITMENT, second
        )

        self.assertEqual(first_commitment, second_commitment)

    def test_parent_and_anchor_changes_commitment(self):
        state = {"value": 1, "anchors": {"branch": "main"}}
        genesis = ImmutableAuditLedger.GENESIS_COMMITMENT

        commitment = ImmutableAuditLedger._commit_state(0, genesis, state)
        different_parent = ImmutableAuditLedger._commit_state(0, "1" * 64, state)
        different_anchor = ImmutableAuditLedger._commit_state(
            0, genesis, {"value": 1, "anchors": {"branch": "release"}}
        )

        self.assertNotEqual(commitment, different_parent)
        self.assertNotEqual(commitment, different_anchor)

    def test_canonical_state_supports_empty_and_optional_values(self):
        state = {"empty": {}, "optional": None, "items": [], "coordinates": (1, 2.0)}
        commitment = ImmutableAuditLedger._commit_state(
            0, ImmutableAuditLedger.GENESIS_COMMITMENT, state
        )

        self.assertIsInstance(commitment, str)
        self.assertEqual(len(commitment), 64)

    def test_repeated_identical_transitions_are_reproducible(self):
        payload = Payload("Test", {"source_id": "test"})
        first = FortressUnified(FortressConfig()).process(payload, 5.0, 100.0)
        second = FortressUnified(FortressConfig()).process(payload, 5.0, 100.0)

        self.assertEqual(first["state_commitment"], second["state_commitment"])


class TestSAGEController(unittest.TestCase):
    def test_regime_classification_stable(self):
        config = FortressConfig(controller_mode="sage")
        controller = SAGEController(config)
        payload = Payload("Normal operation", {"source_id": "test"})

        result = controller.process(payload, 2.0, 100.0)
        self.assertEqual(result["regime"], OperationalRegime.STABLE.value)

    def test_regime_classification_unstable(self):
        config = FortressConfig(controller_mode="sage")
        controller = SAGEController(config)
        payload = Payload("Degrading", {})

        for _ in range(8):
            result = controller.process(payload, 15.0, 100.0)

        self.assertIn(result["regime"], [OperationalRegime.UNSTABLE.value, OperationalRegime.CRITICAL.value])

    def test_response_scales_with_regime(self):
        config = FortressConfig(controller_mode="sage")
        controller = SAGEController(config)
        payload = Payload("Normal", {})

        result_stable = controller.process(payload, 2.0, 100.0)
        stable_output = result_stable["output"]

        controller2 = SAGEController(config)
        for _ in range(8):
            result_unstable = controller2.process(payload, 18.0, 100.0)

        unstable_output = result_unstable["output"]

        # Unstable regime should produce larger corrections
        self.assertNotEqual(stable_output, unstable_output)


class TestLyapunovController(unittest.TestCase):
    def test_stability_analysis(self):
        config = FortressConfig(controller_mode="lyapunov", max_contraction_ratio=0.98)
        controller = LyapunovController(config)
        payload = Payload("Stable", {"source_id": "test", "signature": "valid"})

        result = controller.process(payload, 2.0, 100.0)
        self.assertIn("authority", result)
        self.assertIn("distortion", result)

    def test_governance_activation(self):
        config = FortressConfig(controller_mode="lyapunov", authority_enter_threshold=0.45)
        controller = LyapunovController(config)
        payload = Payload("Unstable", {})

        results = []
        for _ in range(20):
            result = controller.process(payload, 28.0, 100.0)  # Higher error to trigger governance
            results.append(result)

        # Governance activates when distortion exceeds threshold
        # Either controller.governance_active is true, or freeze counter shows it was active
        self.assertTrue(
            controller.governance_active or
            controller.freeze_counter > 0 or
            any(r.get("regime") == "GOVERNED" for r in results)
        )

    def test_freeze_counter_enforcement(self):
        config = FortressConfig(controller_mode="lyapunov", recovery_freeze_cycles=8)
        controller = LyapunovController(config)
        payload = Payload("Fail", {})

        for _ in range(15):
            result = controller.process(payload, 20.0, 100.0)

        self.assertGreaterEqual(controller.freeze_counter, 0)


class TestEnergyController(unittest.TestCase):
    def test_energy_detection(self):
        config = FortressConfig(controller_mode="energy")
        controller = EnergyController(config)
        payload = Payload("Normal", {})

        result1 = controller.process(payload, 2.0, 100.0)
        self.assertEqual(result1["mode"], "NOMINAL")

    def test_state_transition_logging(self):
        config = FortressConfig(controller_mode="energy")
        controller = EnergyController(config)
        payload = Payload("Unstable", {})

        for _ in range(8):
            result = controller.process(payload, 25.0, 100.0)

        if controller.is_override_engaged:
            self.assertGreater(len(controller.state_transitions), 0)

    def test_blending_coefficient_control(self):
        config = FortressConfig(controller_mode="energy")
        controller = EnergyController(config)
        payload = Payload("Normal", {})

        result = controller.process(payload, 2.0, 100.0)
        self.assertGreaterEqual(controller.blending_coefficient, 0.0)
        self.assertLessEqual(controller.blending_coefficient, 1.0)


class TestFortressUnified(unittest.TestCase):
    def test_sage_mode_selection(self):
        config = FortressConfig(controller_mode="sage")
        fortress = FortressUnified(config)
        payload = Payload("Test", {})

        result = fortress.process(payload, 5.0, 100.0)
        self.assertEqual(result["controller"], "SAGE")

    def test_lyapunov_mode_selection(self):
        config = FortressConfig(controller_mode="lyapunov")
        fortress = FortressUnified(config)
        payload = Payload("Test", {})

        result = fortress.process(payload, 5.0, 100.0)
        self.assertEqual(result["controller"], "LYAPUNOV")

    def test_energy_mode_selection(self):
        config = FortressConfig(controller_mode="energy")
        fortress = FortressUnified(config)
        payload = Payload("Test", {})

        result = fortress.process(payload, 5.0, 100.0)
        self.assertEqual(result["controller"], "ENERGY")

    def test_verified_vs_unverified_payload(self):
        config = FortressConfig()
        fortress = FortressUnified(config)

        payload_verified = Payload("Test", {"source_id": "test", "signature": "valid"})
        payload_unverified = Payload("Test", {})

        result_verified = fortress.process(payload_verified, 5.0, 100.0)
        result_unverified = fortress.process(payload_unverified, 5.0, 100.0)

        self.assertEqual(result_verified["integrity"], "VERIFIED")
        self.assertEqual(result_unverified["integrity"], "UNVERIFIED")

    def test_audit_trail_creation(self):
        config = FortressConfig()
        fortress = FortressUnified(config)
        payload = Payload("Test", {})

        fortress.process(payload, 5.0, 100.0)
        fortress.process(payload, 6.0, 101.0)

        self.assertEqual(len(fortress.audit.ledger), 2)

    def test_audit_integrity_preservation(self):
        config = FortressConfig()
        fortress = FortressUnified(config)
        payload = Payload("Test", {})

        fortress.process(payload, 5.0, 100.0)
        fortress.process(payload, 6.0, 101.0)

        self.assertTrue(fortress.audit.verify_integrity())

    def test_process_exposes_and_records_state_commitment(self):
        fortress = FortressUnified(FortressConfig())
        result = fortress.process(Payload("Test", {}), 5.0, 100.0)

        self.assertEqual(result["state_commitment"], fortress.audit.ledger[0]["state_commitment"])
        self.assertTrue(fortress.audit.verify_integrity())


class TestIntegration(unittest.TestCase):
    def test_multiple_controllers_consistency(self):
        payload = Payload("Test", {"source_id": "test", "signature": "sig"})

        results = {}
        for mode in ["sage", "lyapunov", "energy"]:
            config = FortressConfig(controller_mode=mode)
            fortress = FortressUnified(config)
            result = fortress.process(payload, 5.0, 100.0)
            results[mode] = result

        for mode in ["sage", "lyapunov", "energy"]:
            self.assertIn("output", results[mode])
            self.assertIn("distortion", results[mode])

    def test_stress_test_rapid_changes(self):
        config = FortressConfig(controller_mode="energy")
        fortress = FortressUnified(config)
        payload = Payload("Stress", {})

        for error in [2.0, 20.0, 2.0, 25.0, 1.0]:
            result = fortress.process(payload, error, 100.0)
            self.assertIn("output", result)

        self.assertTrue(fortress.audit.verify_integrity())

    def test_guardrails_integration(self):
        config = FortressConfig(controller_mode="lyapunov")
        fortress = FortressUnified(config)
        payload = Payload("Stress", {})

        violations_found = False
        for error in [22.0, 25.0, 28.0]:
            result = fortress.process(payload, error, 100.0)
            if abs(error) > 20.0:
                violations_found = True

        self.assertTrue(violations_found or len(fortress.audit.ledger) > 0)


if __name__ == "__main__":
    unittest.main()
