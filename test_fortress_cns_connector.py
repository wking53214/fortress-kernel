"""The connected half: what fortress-kernel's verdicts become when CNS is installed.

Skipped as a module when CNS is absent. The independence half, which must hold
in both environments, is in ``test_fortress_cns_independence.py`` and never
skips.
"""

import itertools
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

cns_gate = pytest.importorskip(
    "cns.gate", reason="cns not installed; run in an environment with fortress-kernel[cns]"
)

from fortress_cns_connector import (  # noqa: E402
    AuditChainGate,
    InvariantGate,
    MandateGate,
    NumericSafetyGate,
    cns_available,
    cns_chain,
    to_cns_result,
)
from fortress_unified import (  # noqa: E402
    FortressConfig,
    FortressUnified,
    ImmutableAuditLedger,
    IntegrityLayer,
    InvariantMonitor,
    MandateLayer,
    Payload,
)

NAN = float("nan")
INF = float("inf")

PASS = cns_gate.GateOutcome.PASS
RETRY = cns_gate.GateOutcome.RETRY
BREACH = cns_gate.GateOutcome.TERMINAL_BREACH
ALPHA = cns_gate.GatePosition.ALPHA
OMEGA = cns_gate.GatePosition.OMEGA

SIGNED = Payload("Calm", {"source_id": "s", "signature": "sig"})


def invariant_candidate(state=50.0, distortion=0.5, error=5.0, volatility=2.0):
    return {"state": state, "distortion": distortion, "error": error, "volatility": volatility}


def mandate_candidate(delta=1.5, current=50.0, target=100.0, volatility=2.0):
    return {
        "action": {"delta": delta},
        "current_kpi": current,
        "target_kpi": target,
        "volatility": volatility,
    }


def kernel_with_history(errors=(1.0, 2.0, 1.5), mode="energy"):
    fortress = FortressUnified(FortressConfig(controller_mode=mode))
    for error in errors:
        fortress.process(SIGNED, error, 100.0)
    return fortress


def deep_list(depth):
    value = []
    for _ in range(depth):
        value = [value]
    return value


def deep_dict(depth):
    value = {}
    for _ in range(depth):
        value = {"k": value}
    return value


def cyclic_list():
    cycle = []
    cycle.append(cycle)
    return cycle


def cyclic_dict():
    cycle = {}
    cycle["self"] = cycle
    return cycle


def limit_int_digits(case):
    """Make the int-to-str limit (4300 digits) hold, so a 5000 digit int is refused."""
    if not hasattr(sys, "set_int_max_str_digits"):
        case.skipTest("this Python has no int-to-str digit limit")
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    case.addCleanup(sys.set_int_max_str_digits, previous)


HUGE = 10 ** 5000


class TestAvailabilityAndShape(unittest.TestCase):
    def test_cns_is_seen_as_available(self):
        self.assertIs(cns_available(), True)

    def test_each_gate_declares_the_end_it_belongs_to(self):
        self.assertIs(NumericSafetyGate().position, ALPHA)
        self.assertIs(MandateGate().position, ALPHA)
        self.assertIs(InvariantGate().position, OMEGA)
        self.assertIs(AuditChainGate().position, OMEGA)

    def test_every_gate_satisfies_the_cns_gate_protocol(self):
        for gate in (NumericSafetyGate(), MandateGate(), InvariantGate(), AuditChainGate()):
            with self.subTest(gate=gate.name):
                self.assertIsInstance(gate, cns_gate.Gate)
        gates = (NumericSafetyGate(), MandateGate(), InvariantGate(), AuditChainGate())
        self.assertEqual(
            [g.name for g in gates],
            ["numeric_safety", "mandate", "invariants", "audit_chain"],
        )

    def test_a_result_carries_the_position_of_the_gate_that_issued_it(self):
        ledger = kernel_with_history().audit
        issued = [
            (NumericSafetyGate(), {"error": 1.0}, ALPHA),
            (MandateGate(), mandate_candidate(), ALPHA),
            (InvariantGate(), invariant_candidate(), OMEGA),
            (AuditChainGate(), ledger, OMEGA),
        ]
        for gate, candidate, end in issued:
            with self.subTest(gate=gate.name):
                result = gate.check(candidate)
                self.assertIs(result.position, end)
                self.assertIs(gate.position, end)
                self.assertEqual(result.gate, gate.name)

    def test_the_chain_has_both_ends_each_in_its_own_slot(self):
        chain = cns_chain()
        self.assertEqual([g.name for g in chain.alpha], ["numeric_safety", "mandate"])
        self.assertEqual([g.name for g in chain.omega], ["invariants", "audit_chain"])
        self.assertEqual(chain.misplaced(), ())
        self.assertIs(chain.complete(), True)


class TestNumericSafetyGate(unittest.TestCase):
    def test_a_finite_error_passes_before_the_work_starts(self):
        for error in (0.0, 5.0, -3.0, 25.0, 1e6, 7):
            with self.subTest(error=error):
                verdict = NumericSafetyGate().check({"error": error})
                self.assertIs(verdict.outcome, PASS)
                self.assertIs(verdict.position, ALPHA)
                self.assertFalse(verdict.blocking())

    def test_nan_and_infinities_are_a_terminal_breach_with_the_kernels_own_reason(self):
        for error in (NAN, INF, -INF):
            with self.subTest(error=error):
                verdict = NumericSafetyGate().check({"error": error})
                self.assertIs(verdict.outcome, BREACH)
                self.assertTrue(verdict.blocking())
                self.assertIn("Numeric Safety Exception", verdict.reason)

    def test_an_int_too_large_for_the_kernels_float_maths_is_refused_not_raised(self):
        verdict = NumericSafetyGate().check({"error": 10 ** 400})
        self.assertIs(verdict.outcome, BREACH)
        self.assertIn("OverflowError", verdict.reason)
        self.assertTrue(verdict.bound())

    def test_the_gate_agrees_with_the_kernel_on_every_error_it_is_given(self):
        for error in (0.0, 5.0, -3.0, 25.0, 1e6, 1e308, NAN, INF, -INF, 10 ** 400):
            with self.subTest(error=error):
                try:
                    IntegrityLayer(FortressConfig()).analyze(Payload(""), error)
                except (ValueError, OverflowError):
                    refused = True
                else:
                    refused = False
                verdict = NumericSafetyGate().check({"error": error})
                self.assertIs(verdict.outcome is PASS, not refused)

    def test_the_gate_agrees_with_what_process_does_with_the_same_error(self):
        for error in (0.0, 5.0, -3.0, 25.0, NAN, INF, -INF):
            with self.subTest(error=error):
                verdict = NumericSafetyGate().check({"error": error})
                fortress = FortressUnified(FortressConfig())
                if verdict.outcome is PASS:
                    fortress.process(Payload("t", {}), error, 100.0)
                else:
                    with self.assertRaises(ValueError):
                        fortress.process(Payload("t", {}), error, 100.0)
                    # process refused before the controller or the audit ran.
                    self.assertEqual(fortress.audit.ledger, [])

    def test_the_gate_does_not_touch_a_live_integrity_layer(self):
        fortress = kernel_with_history()
        before = list(fortress.integrity.error_history_window)
        NumericSafetyGate().check({"error": 99.0})
        NumericSafetyGate().check({"error": NAN})
        self.assertEqual(list(fortress.integrity.error_history_window), before)

    def test_each_check_uses_a_throwaway_layer_so_no_history_accumulates(self):
        seen = []
        real = IntegrityLayer.analyze

        def spy(layer, payload, error):
            seen.append(layer)
            return real(layer, payload, error)

        with mock.patch.object(IntegrityLayer, "analyze", spy):
            NumericSafetyGate().check({"error": 1.0})
            NumericSafetyGate().check({"error": 2.0})
        self.assertEqual(len(seen), 2)
        self.assertIsNot(seen[0], seen[1])
        self.assertEqual([len(layer.error_history_window) for layer in seen], [1, 1])

    def test_the_verdict_is_bound_to_the_error_it_judged(self):
        gate = NumericSafetyGate()
        verdict = gate.check({"error": 5.0})
        self.assertEqual(cns_gate.unbound([verdict]), ())
        self.assertEqual(verdict.subject, "error")
        self.assertEqual(verdict.subject_digest, cns_gate.subject_digest({"error": 5.0}))
        self.assertTrue(verdict.binds("error", gate.digest({"error": 5.0})))
        self.assertFalse(verdict.binds("error", gate.digest({"error": 6.0})))
        self.assertFalse(verdict.binds("other", gate.digest({"error": 5.0})))

    def test_a_non_finite_error_is_still_bound_and_each_kind_digests_differently(self):
        gate = NumericSafetyGate()
        digests = set()
        for error, tag in ((NAN, "nan"), (INF, "inf"), (-INF, "-inf")):
            verdict = gate.check({"error": error})
            self.assertTrue(verdict.bound())
            self.assertEqual(
                verdict.subject_digest,
                cns_gate.subject_digest({"error": {"nonfinite": tag}}),
            )
            digests.add(verdict.subject_digest)
        digests.add(gate.digest({"error": 5.0}))
        self.assertEqual(len(digests), 4)

    def test_numpy_scalars_digest_like_plain_numbers(self):
        gate = NumericSafetyGate()
        self.assertEqual(gate.digest({"error": np.float64(5.0)}), gate.digest({"error": 5.0}))
        self.assertEqual(gate.digest({"error": np.float32(5.0)}), gate.digest({"error": 5.0}))
        self.assertEqual(gate.digest({"error": np.int64(5)}), gate.digest({"error": 5}))
        self.assertIs(gate.check({"error": np.float64(NAN)}).outcome, BREACH)

    def test_a_candidate_that_is_not_the_right_shape_is_refused_loudly(self):
        gate = NumericSafetyGate()
        for bad in (5.0, "5", None, [5.0]):
            with self.subTest(candidate=bad), self.assertRaises(TypeError):
                gate.check(bad)
        with self.assertRaises(ValueError):
            gate.check({})
        for bad in ("5", None, [1.0], 1j):
            with self.subTest(error=bad), self.assertRaises(TypeError):
                gate.check({"error": bad})


class TestMandateGate(unittest.TestCase):
    def test_a_delta_inside_the_mandate_passes(self):
        verdict = MandateGate().check(mandate_candidate(delta=1.5))
        self.assertIs(verdict.outcome, PASS)
        self.assertIs(verdict.position, ALPHA)

    def test_a_clamped_delta_is_a_retry_carrying_the_kernels_own_repair(self):
        verdict = MandateGate().check(mandate_candidate(delta=100.0))
        enforced = MandateLayer.enforce({"delta": 100.0}, 50.0, 100.0, 2.0)["delta"]
        self.assertIs(verdict.outcome, RETRY)
        self.assertTrue(verdict.blocking())
        self.assertIn(repr(enforced), verdict.reason)
        self.assertIn("100.0", verdict.reason)

    def test_the_gate_agrees_with_enforce_across_a_grid(self):
        gate = MandateGate()
        seen = set()
        grid = itertools.product(
            (-200.0, -30.0, -1.5, 0.0, 1.5, 30.0, 100.0),
            (0.0, 50.0, 100.0, 400.0),
            (100.0,),
            (0.0, 2.0, 50.0),
        )
        for delta, current, target, volatility in grid:
            with self.subTest(delta=delta, current=current, volatility=volatility):
                enforced = MandateLayer.enforce(
                    {"delta": delta}, current, target, volatility
                )["delta"]
                verdict = gate.check(mandate_candidate(delta, current, target, volatility))
                if enforced == delta:
                    self.assertIs(verdict.outcome, PASS)
                else:
                    self.assertIs(verdict.outcome, RETRY)
                    self.assertIn(repr(enforced), verdict.reason)
                seen.add(verdict.outcome)
        self.assertEqual(seen, {PASS, RETRY})

    def test_the_proposed_action_is_never_mutated(self):
        action = {"delta": 100.0, "note": "keep"}
        MandateGate().check(
            {"action": action, "current_kpi": 50.0, "target_kpi": 100.0, "volatility": 2.0}
        )
        self.assertEqual(action, {"delta": 100.0, "note": "keep"})

    def test_a_missing_delta_is_read_as_zero_like_the_kernel_reads_it(self):
        within = MandateGate().check(
            {"action": {}, "current_kpi": 50.0, "target_kpi": 100.0, "volatility": 1.0}
        )
        self.assertIs(within.outcome, PASS)
        far = MandateGate().check(
            {"action": {}, "current_kpi": 500.0, "target_kpi": 100.0, "volatility": 1.0}
        )
        self.assertIs(far.outcome, RETRY)
        self.assertIn("-385.0", far.reason)

    def test_non_finite_input_is_a_terminal_breach_where_the_kernel_passes_it_through(self):
        # The kernel's own behaviour, shown so the test says what it guards.
        self.assertTrue(np.isnan(MandateLayer.enforce({"delta": NAN}, 50.0, 100.0, 1.0)["delta"]))
        self.assertEqual(MandateLayer.enforce({"delta": 500.0}, NAN, 100.0, 1.0)["delta"], 28.0)
        cases = {
            "delta": mandate_candidate(delta=NAN),
            "current_kpi": mandate_candidate(current=NAN),
            "target_kpi": mandate_candidate(target=NAN),
            "volatility": mandate_candidate(volatility=NAN),
        }
        for name, candidate in cases.items():
            with self.subTest(nan=name):
                verdict = MandateGate().check(candidate)
                self.assertIs(verdict.outcome, BREACH)
                self.assertIn("non-finite", verdict.reason)
                self.assertIn(name, verdict.reason)
        for candidate in (
            mandate_candidate(delta=INF),
            mandate_candidate(current=INF),
            mandate_candidate(target=-INF),
            mandate_candidate(volatility=INF),
        ):
            with self.subTest(candidate=candidate):
                self.assertIs(MandateGate().check(candidate).outcome, BREACH)

    def test_an_error_the_kernel_raises_is_a_terminal_breach_never_a_pass(self):
        candidate = mandate_candidate(volatility=-1 / 0.15)  # denominator is exactly zero
        with self.assertRaises(ZeroDivisionError):
            MandateLayer.enforce({"delta": 1.0}, 50.0, 100.0, -1 / 0.15)
        verdict = MandateGate().check(candidate)
        self.assertIs(verdict.outcome, BREACH)
        self.assertIn("ZeroDivisionError", verdict.reason)

    def test_the_verdict_is_bound_to_exactly_what_the_kernel_read(self):
        gate = MandateGate()
        candidate = {
            "action": {"delta": 100.0, "note": "not judged"},
            "current_kpi": 50.0,
            "target_kpi": 100.0,
            "volatility": 2.0,
        }
        expected = cns_gate.subject_digest(
            {
                "action": {"delta": 100.0},
                "current_kpi": 50.0,
                "target_kpi": 100.0,
                "volatility": 2.0,
            }
        )
        verdict = gate.check(candidate)
        self.assertEqual(verdict.subject, "action")
        self.assertEqual(verdict.subject_digest, expected)
        self.assertEqual(cns_gate.unbound([verdict]), ())
        self.assertFalse(verdict.binds("action", gate.digest(mandate_candidate(delta=99.0))))

    def test_a_candidate_that_is_not_the_right_shape_is_refused_loudly(self):
        gate = MandateGate()
        with self.assertRaises(TypeError):
            gate.check([1.0])
        with self.assertRaises(ValueError):
            gate.check({"action": {}})
        with self.assertRaises(TypeError):
            gate.check({**mandate_candidate(), "action": 5})
        with self.assertRaises(TypeError):
            gate.check(mandate_candidate(delta="1.0"))


class TestInvariantGate(unittest.TestCase):
    VIOLATING = {
        "STATE_DIVERGENCE": invariant_candidate(state=300.0),
        "DISTORTION_OVERFLOW": invariant_candidate(distortion=0.90),
        "MODEL_FAILURE": invariant_candidate(error=25.0),
        "VOLATILITY_SPIKE": invariant_candidate(volatility=50.0),
    }

    def test_no_violation_is_a_pass_at_the_omega_end(self):
        verdict = InvariantGate().check(invariant_candidate())
        self.assertIs(verdict.outcome, PASS)
        self.assertIs(verdict.position, OMEGA)
        self.assertFalse(verdict.blocking())

    def test_each_hard_bound_is_a_terminal_breach_naming_it(self):
        for name, candidate in self.VIOLATING.items():
            with self.subTest(violation=name):
                verdict = InvariantGate().check(candidate)
                self.assertIs(verdict.outcome, BREACH)
                self.assertIn(name, verdict.reason)
                self.assertIs(cns_gate.resolve([verdict]), BREACH)

    def test_every_violation_is_reported_in_the_kernels_order(self):
        verdict = InvariantGate().check(invariant_candidate(300.0, 0.9, 25.0, 50.0))
        self.assertEqual(
            verdict.reason,
            "invariant violation: STATE_DIVERGENCE, DISTORTION_OVERFLOW, "
            "MODEL_FAILURE, VOLATILITY_SPIKE",
        )

    def test_the_gate_agrees_with_the_monitor_across_a_grid(self):
        gate = InvariantGate()
        outcomes = set()
        grid = itertools.product(
            (0.0, 249.9, 250.0, 250.1, -300.0),
            (0.0, 0.85, 0.86),
            (-50.0, 0.0, 20.0, 20.1, 25.0),
            (0.0, 40.0, 40.1),
        )
        for state, distortion, error, volatility in grid:
            with self.subTest(s=state, d=distortion, e=error, v=volatility):
                native = InvariantMonitor.check(state, distortion, error, volatility)
                verdict = gate.check(invariant_candidate(state, distortion, error, volatility))
                self.assertIs(verdict.outcome is PASS, native == [])
                self.assertIs(verdict.outcome is BREACH, native != [])
                for name in native:
                    self.assertIn(name, verdict.reason)
                outcomes.add(verdict.outcome)
        self.assertEqual(outcomes, {PASS, BREACH})

    def test_the_gate_keeps_the_kernels_verdict_where_the_kernel_is_lenient(self):
        # The monitor compares `error > 20.0` without abs(), so a large negative
        # error is not flagged. The connector reports that, it does not correct it.
        self.assertEqual(InvariantMonitor.check(50.0, 0.5, -50.0, 2.0), [])
        self.assertIs(InvariantGate().check(invariant_candidate(error=-50.0)).outcome, PASS)

    def test_non_finite_input_is_a_terminal_breach_where_the_monitor_finds_nothing(self):
        self.assertEqual(InvariantMonitor.check(NAN, NAN, NAN, NAN), [])
        self.assertEqual(InvariantMonitor.check(50.0, -INF, -INF, -INF), [])
        for key in ("state", "distortion", "error", "volatility"):
            for bad in (NAN, -INF):
                with self.subTest(field=key, value=bad):
                    verdict = InvariantGate().check(invariant_candidate(**{key: bad}))
                    self.assertIs(verdict.outcome, BREACH)
                    self.assertIn("non-finite", verdict.reason)
                    self.assertIn(key, verdict.reason)

    def test_an_infinity_the_monitor_does_flag_reports_both_reasons(self):
        verdict = InvariantGate().check(invariant_candidate(state=INF))
        self.assertIs(verdict.outcome, BREACH)
        self.assertIn("STATE_DIVERGENCE", verdict.reason)
        self.assertIn("non-finite", verdict.reason)

    def test_the_verdict_is_bound_to_the_four_values_it_judged(self):
        gate = InvariantGate()
        candidate = invariant_candidate(300.0)
        verdict = gate.check(candidate)
        self.assertEqual(verdict.subject, "state")
        self.assertEqual(
            verdict.subject_digest,
            cns_gate.subject_digest(
                {"state": 300.0, "distortion": 0.5, "error": 5.0, "volatility": 2.0}
            ),
        )
        self.assertEqual(cns_gate.unbound([verdict]), ())
        # A verdict moved onto a different run's values does not bind.
        self.assertFalse(verdict.binds("state", gate.digest(invariant_candidate(1.0))))
        self.assertTrue(verdict.binds("state", gate.digest(candidate)))

    def test_the_gate_judges_what_process_produced_like_the_kernels_own_test(self):
        fortress = FortressUnified(FortressConfig(controller_mode="lyapunov"))
        for error in (22.0, 25.0, 28.0):
            result = fortress.process(Payload("Stress", {}), error, 100.0)
            verdict = InvariantGate().check(
                {
                    "state": result["output"],
                    "distortion": result["distortion"],
                    "error": error,
                    "volatility": 0.0,
                }
            )
            self.assertIs(verdict.outcome, BREACH)
            self.assertIn("MODEL_FAILURE", verdict.reason)

    def test_a_candidate_that_is_not_the_right_shape_is_refused_loudly(self):
        gate = InvariantGate()
        with self.assertRaises(TypeError):
            gate.check((50.0, 0.5, 5.0, 2.0))
        with self.assertRaises(ValueError):
            gate.check({"state": 1.0})
        with self.assertRaises(TypeError):
            gate.check(invariant_candidate(state=None))


class TestAuditChainGate(unittest.TestCase):
    def test_an_intact_chain_from_a_real_run_passes(self):
        for mode in ("sage", "lyapunov", "energy"):
            with self.subTest(mode=mode):
                fortress = kernel_with_history(mode=mode)
                verdict = AuditChainGate().check(fortress.audit)
                self.assertIs(verdict.outcome, PASS)
                self.assertIs(verdict.position, OMEGA)

    def test_an_empty_ledger_passes_because_the_kernel_says_it_is_intact(self):
        ledger = ImmutableAuditLedger()
        self.assertTrue(ledger.verify_integrity())
        self.assertIs(AuditChainGate().check(ledger).outcome, PASS)

    def test_a_tampered_chain_is_a_terminal_breach(self):
        def edited(ledger):
            ledger.ledger[0]["data"]["live_signal"] = 0.0

        def deleted(ledger):
            ledger.ledger.pop(0)

        def reordered(ledger):
            ledger.ledger.reverse()

        def unsigned(ledger):
            del ledger.ledger[1]["hmac"]

        for label, tamper in (
            ("edited", edited),
            ("deleted", deleted),
            ("reordered", reordered),
            ("unsigned", unsigned),
        ):
            with self.subTest(tamper=label):
                ledger = kernel_with_history().audit
                tamper(ledger)
                self.assertFalse(ledger.verify_integrity())
                verdict = AuditChainGate().check(ledger)
                self.assertIs(verdict.outcome, BREACH)
                self.assertIn("verify_integrity", verdict.reason)
                self.assertTrue(verdict.blocking())

    def test_a_ledger_that_crashes_its_own_verifier_is_a_breach_not_an_exception(self):
        ledger = kernel_with_history().audit
        ledger.ledger.append("not a record")
        with self.assertRaises(Exception):
            ledger.verify_integrity()
        verdict = AuditChainGate().check(ledger)
        self.assertIs(verdict.outcome, BREACH)
        self.assertIn("raised", verdict.reason)

    def test_the_gate_agrees_with_verify_integrity_and_changes_nothing(self):
        ledger = kernel_with_history().audit
        before = json.dumps(ledger.ledger, sort_keys=True)
        for _ in range(2):
            self.assertIs(AuditChainGate().check(ledger).outcome is PASS, ledger.verify_integrity())
            ledger.ledger[0]["data"]["live_signal"] = -1.0
        self.assertNotEqual(before, json.dumps(ledger.ledger, sort_keys=True))
        self.assertEqual(len(ledger.ledger), 3)

    def test_the_verdict_is_bound_to_the_records_and_drifts_out_of_binding(self):
        fortress = kernel_with_history()
        gate = AuditChainGate()
        verdict = gate.check(fortress.audit)
        self.assertEqual(verdict.subject, "audit_ledger")
        self.assertEqual(cns_gate.unbound([verdict]), ())
        self.assertTrue(verdict.binds("audit_ledger", gate.digest(fortress.audit)))
        # The same verdict does not vouch for a ledger that has grown since.
        fortress.process(SIGNED, 1.0, 100.0)
        self.assertFalse(verdict.binds("audit_ledger", gate.digest(fortress.audit)))
        # Nor for one that was edited in place.
        other = kernel_with_history().audit
        stale = gate.check(other)
        other.ledger[0]["data"]["live_signal"] = 0.0
        self.assertFalse(stale.binds("audit_ledger", gate.digest(other)))

    def test_the_digest_is_the_cns_digest_of_the_records_and_never_holds_the_key(self):
        fortress = kernel_with_history()
        oracle = cns_gate.subject_digest({"records": json.loads(json.dumps(fortress.audit.ledger))})
        self.assertEqual(AuditChainGate().digest(fortress.audit), oracle)
        keyed = ImmutableAuditLedger(audit_key="a-different-key")
        keyed.append("e", {"x": 1})
        self.assertNotIn("a-different-key", json.dumps(keyed.ledger))

    def test_numpy_scalars_in_a_ledger_do_not_change_its_digest(self):
        fortress = FortressUnified(FortressConfig())
        fortress.process(SIGNED, np.float64(5.0), np.float64(100.0))
        fortress.process(SIGNED, np.float64(2.0), 100.0)
        ledger = fortress.audit
        self.assertIs(AuditChainGate().check(ledger).outcome, PASS)
        oracle = cns_gate.subject_digest({"records": json.loads(json.dumps(ledger.ledger))})
        self.assertEqual(AuditChainGate().digest(ledger), oracle)
        # Whatever numpy's repr is on this version, the digest never carries it.
        record = ImmutableAuditLedger()
        record.append("e", {"x": np.float64(1.5)})
        plain = ImmutableAuditLedger()
        plain.ledger = json.loads(json.dumps(record.ledger))
        self.assertEqual(AuditChainGate().digest(record), AuditChainGate().digest(plain))

    def test_content_cns_cannot_describe_gives_an_unbound_breach_never_a_pass(self):
        ledger = kernel_with_history().audit
        ledger.ledger[0]["data"]["extra"] = {1, 2}
        self.assertFalse(ledger.verify_integrity())
        gate = AuditChainGate()
        with self.assertRaises(TypeError):
            gate.digest(ledger)
        verdict = gate.check(ledger)
        self.assertIs(verdict.outcome, BREACH)
        self.assertFalse(verdict.bound())
        self.assertEqual(verdict.subject_digest, "")
        self.assertIn("unbound", verdict.reason)
        self.assertEqual(cns_gate.unbound([verdict]), ("audit_chain",))
        self.assertFalse(verdict.binds("audit_ledger", ""))

    def test_a_tampered_ledger_cns_cannot_describe_is_an_unbound_breach_never_an_exception(self):
        # Each of these is something the kernel's own verify_integrity() refuses
        # (False) or chokes on, and each used to escape the gate as an exception.
        def non_string_key(key):
            def tamper(ledger):
                ledger.ledger[0]["data"][key] = 2
            return tamper

        def put(value, key="extra"):
            def tamper(ledger):
                ledger.ledger[0]["data"][key] = value
            return tamper

        def lose_the_list(ledger):
            del ledger.ledger

        cases = (
            ("int key", non_string_key(1)),
            ("bool key", non_string_key(True)),
            ("tuple key", non_string_key((1, 2))),
            ("None key", non_string_key(None)),
            ("float key", non_string_key(1.5)),
            ("lone surrogate in a value", put("\ud800")),
            ("lone surrogate in a key", put(1, key="\ud800")),
            ("set", put({1, 2})),
            ("bytes", put(b"raw")),
            ("arbitrary object", put(object())),
            ("nesting 3000 deep", put(deep_list(3000))),
            ("nested mappings 3000 deep", put(deep_dict(3000))),
            ("cyclic list", put(cyclic_list())),
            ("cyclic mapping", put(cyclic_dict())),
            ("the ledger list is gone", lose_the_list),
        )
        for label, tamper in cases:
            with self.subTest(tamper=label):
                ledger = kernel_with_history().audit
                tamper(ledger)
                gate = AuditChainGate()
                verdict = gate.check(ledger)
                self.assertIs(verdict.outcome, BREACH)
                self.assertTrue(verdict.blocking())
                self.assertFalse(verdict.bound())
                self.assertEqual(verdict.subject_digest, "")
                self.assertIn("unbound", verdict.reason)
                self.assertEqual(cns_gate.unbound([verdict]), ("audit_chain",))
                with self.assertRaises(TypeError):
                    gate.digest(ledger)

    def test_a_ledger_the_kernel_accepts_is_never_an_exception_however_deeply_it_nests(self):
        # CNS recurses a few hundred levels at most; the kernel accepts a little
        # more than that. Either the verdict is bound and a pass, or it is an
        # unbound breach. It is never an exception and never an unbound pass.
        for depth in (10, 100, 300, 400):
            with self.subTest(depth=depth):
                ledger = ImmutableAuditLedger()
                ledger.append("event", {"meta": deep_dict(depth)})
                self.assertTrue(ledger.verify_integrity())
                verdict = AuditChainGate().check(ledger)
                self.assertEqual(verdict.bound(), verdict.outcome is PASS)
                self.assertIs(verdict.outcome is PASS or verdict.outcome is BREACH, True)

    def test_only_a_real_true_from_verify_integrity_is_an_intact_chain(self):
        ledger = kernel_with_history().audit
        for returned in (None, 1, "yes", [1], 0, False, ""):
            with self.subTest(returned=repr(returned)):
                with mock.patch.object(
                    ImmutableAuditLedger, "verify_integrity", return_value=returned
                ):
                    verdict = AuditChainGate().check(ledger)
                self.assertIs(verdict.outcome, BREACH)
                self.assertIn("verify_integrity", verdict.reason)
        with mock.patch.object(ImmutableAuditLedger, "verify_integrity", return_value=True):
            self.assertIs(AuditChainGate().check(ledger).outcome, PASS)

    def test_a_candidate_that_is_not_a_ledger_is_refused_loudly(self):
        for bad in (kernel_with_history(), [], None, {"records": []}):
            with self.subTest(candidate=type(bad).__name__), self.assertRaises(TypeError):
                AuditChainGate().check(bad)


class TestIntegersTooLargeToRender(unittest.TestCase):
    """CPython refuses to render an int of more than 4300 digits, and CNS renders ints."""

    def setUp(self):
        limit_int_digits(self)
        with self.assertRaises(ValueError):
            str(HUGE)

    def _unbound_breach(self, verdict):
        self.assertIs(verdict.outcome, BREACH)
        self.assertTrue(verdict.blocking())
        self.assertFalse(verdict.bound())
        self.assertIn("unbound", verdict.reason)
        self.assertLess(len(verdict.reason), 500)

    def test_numeric_safety_returns_a_verdict_for_a_huge_error(self):
        for error in (HUGE, -HUGE):
            with self.subTest(error=error > 0):
                self._unbound_breach(NumericSafetyGate().check({"error": error}))

    def test_mandate_returns_a_verdict_for_a_huge_value_in_any_position(self):
        for key in ("delta", "current_kpi", "target_kpi", "volatility"):
            for value in (HUGE, -HUGE):
                with self.subTest(field=key, positive=value > 0):
                    candidate = mandate_candidate()
                    if key == "delta":
                        candidate["action"]["delta"] = value
                    else:
                        candidate[key] = value
                    self._unbound_breach(MandateGate().check(candidate))

    def test_a_clamped_huge_delta_is_reported_without_rendering_it(self):
        verdict = MandateGate().check(mandate_candidate(delta=HUGE))
        self._unbound_breach(verdict)
        self.assertIn("outside the mandate", verdict.reason)
        self.assertIn("13.46", verdict.reason)

    def test_invariants_returns_a_verdict_for_a_huge_value_in_any_field(self):
        for key in ("state", "distortion", "error", "volatility"):
            for value in (HUGE, -HUGE):
                with self.subTest(field=key, positive=value > 0):
                    candidate = invariant_candidate()
                    candidate[key] = value
                    self._unbound_breach(InvariantGate().check(candidate))

    def test_an_int_that_can_still_be_rendered_stays_bound(self):
        verdict = InvariantGate().check(invariant_candidate(error=-(10 ** 400)))
        self.assertIs(verdict.outcome, PASS)
        self.assertTrue(verdict.bound())

    def test_digest_raises_type_error_like_any_content_cns_cannot_describe(self):
        with self.assertRaises(TypeError):
            InvariantGate().digest(invariant_candidate(state=HUGE))


class TestTranslation(unittest.TestCase):
    def test_a_passed_verdict_is_pass_a_repairable_one_is_retry_and_the_rest_are_terminal(self):
        content = {"state": 1.0}
        passed = to_cns_result("invariants", passed=True, content=content)
        retry = to_cns_result("mandate", passed=False, retryable=True, content=content, reason="r")
        breach = to_cns_result("invariants", passed=False, content=content, reason="b")
        self.assertEqual((passed.outcome, retry.outcome, breach.outcome), (PASS, RETRY, BREACH))
        self.assertEqual((retry.reason, breach.reason), ("r", "b"))
        self.assertEqual(
            (passed.position, retry.position, breach.position), (OMEGA, ALPHA, OMEGA)
        )
        self.assertTrue(all(r.subject_digest == cns_gate.subject_digest(content)
                            for r in (passed, retry, breach)))

    def test_a_pass_on_content_cns_cannot_describe_is_not_allowed_to_stand(self):
        verdict = to_cns_result("audit_chain", passed=True, content={"records": {1, 2}})
        self.assertIs(verdict.outcome, BREACH)
        self.assertEqual(verdict.subject_digest, "")
        self.assertFalse(verdict.bound())

    def test_content_cns_trips_over_is_an_unbound_breach_naming_what_tripped_it(self):
        limit_int_digits(self)
        cases = (
            ("a set", {1, 2}, "TypeError"),
            ("a non-string key", {1: "a"}, "KeyError"),
            ("a lone surrogate", "\ud800", "UnicodeEncodeError"),
            ("an integer of 5000 digits", HUGE, "ValueError"),
            ("nesting past the recursion limit", deep_list(3000), "RecursionError"),
            ("a cycle", cyclic_list(), "RecursionError"),
        )
        for label, value, error in cases:
            with self.subTest(content=label):
                verdict = to_cns_result("audit_chain", passed=True, content={"records": value})
                self.assertIs(verdict.outcome, BREACH)
                self.assertFalse(verdict.bound())
                self.assertEqual(verdict.subject_digest, "")
                self.assertIn("unbound", verdict.reason)
                self.assertIn(error, verdict.reason)

    def test_the_subject_label_defaults_per_gate_and_can_be_named(self):
        defaults = {
            "numeric_safety": "error",
            "mandate": "action",
            "invariants": "state",
            "audit_chain": "audit_ledger",
        }
        for gate, subject in defaults.items():
            self.assertEqual(to_cns_result(gate, passed=True, content={}).subject, subject)
        named = InvariantGate(subject="run-7").check(invariant_candidate())
        self.assertEqual(named.subject, "run-7")
        with self.assertRaises(ValueError):
            InvariantGate(subject="")

    def test_an_unknown_gate_name_is_refused(self):
        with self.assertRaises(ValueError):
            to_cns_result("hedging", passed=True, content={})


class TestConsumingTheVerdicts(unittest.TestCase):
    def test_a_clean_request_resolves_to_pass_with_every_verdict_bound(self):
        fortress = kernel_with_history()
        error = 5.0
        before = [
            NumericSafetyGate().check({"error": error}),
            MandateGate().check(mandate_candidate(delta=1.5)),
        ]
        produced = []
        real = IntegrityLayer.analyze

        def spy(layer, payload, reading):
            produced.append(real(layer, payload, reading))
            return produced[-1]

        with mock.patch.object(IntegrityLayer, "analyze", spy):
            result = fortress.process(SIGNED, error, 100.0)
        # The volatility the kernel itself produced for this run, not a constant.
        volatility = produced[-1]["volatility"]
        self.assertGreater(volatility, 0.0)
        judged = {"state": result["output"], "distortion": result["distortion"],
                  "error": error, "volatility": volatility}
        after = [
            InvariantGate().check(judged),
            AuditChainGate().check(fortress.audit),
        ]
        verdicts = before + after
        self.assertIs(cns_gate.resolve(verdicts), PASS)
        self.assertEqual(cns_gate.unbound(verdicts), ())
        self.assertTrue(after[0].binds("state", cns_gate.subject_digest(judged)))
        chain = cns_chain()
        self.assertEqual([v.gate for v in before], [g.name for g in chain.alpha])
        self.assertEqual([v.gate for v in after], [g.name for g in chain.omega])
        gates = chain.alpha + chain.omega
        self.assertTrue(all(v.position is g.position for v, g in zip(verdicts, gates)))

    def test_the_readme_example_runs_as_written(self):
        readme = (Path(__file__).resolve().parent / "README.md").read_text()
        section = readme.split("## 8. Connecting to CNS", 1)[1]
        blocks = re.findall(r"```python\n(.*?)```", section, re.S)
        self.assertEqual(len(blocks), 1)
        example = blocks[0]
        self.assertNotIn("volatility\": 0.0", example)
        fortress = kernel_with_history()
        produced = []
        real = IntegrityLayer.analyze

        def spy(layer, payload, reading):
            produced.append(real(layer, payload, reading))
            return produced[-1]

        # The example is handed the names it expects, as a caller would have them.
        scope = {"fortress": fortress, "payload": SIGNED, "error": 5.0, "live_signal": 100.0}
        original_process = fortress.process

        def process_and_note_volatility(*args):
            with mock.patch.object(IntegrityLayer, "analyze", spy):
                out = original_process(*args)
            scope["volatility"] = produced[-1]["volatility"]
            return out

        fortress.process = process_and_note_volatility
        exec(compile(example, "README.md", "exec"), scope)
        verdicts = [scope["admit"], *scope["ran"]]
        self.assertEqual([v.gate for v in verdicts], ["numeric_safety", "invariants", "audit_chain"])
        self.assertIs(cns_gate.resolve(verdicts), PASS)
        self.assertEqual(cns_gate.unbound(verdicts), ())

    def test_resolution_is_fail_closed_across_mixed_verdicts(self):
        passing = NumericSafetyGate().check({"error": 1.0})
        retry = MandateGate().check(mandate_candidate(delta=100.0))
        breach = NumericSafetyGate().check({"error": NAN})
        self.assertIs(cns_gate.resolve([passing, retry]), RETRY)
        self.assertIs(cns_gate.resolve([passing, retry, breach]), BREACH)
        self.assertIs(cns_gate.resolve([breach, passing]), BREACH)


class TestConnectorDoesNotChangeTheKernel(unittest.TestCase):
    ERRORS = (1.0, 2.0, 1.5, 3.0)

    def _run(self, with_gates):
        fortress = FortressUnified(FortressConfig())
        commitments = []
        for error in self.ERRORS:
            if with_gates:
                NumericSafetyGate().check({"error": error})
                MandateGate().check(mandate_candidate())
            result = fortress.process(SIGNED, error, 100.0)
            if with_gates:
                # The value judged is beside the point here: this test is about
                # the gates leaving the kernel's commitments alone.
                InvariantGate().check(
                    invariant_candidate(result["output"], result["distortion"], error, 0.0)
                )
                AuditChainGate().check(fortress.audit)
            commitments.append(result["state_commitment"])
        return fortress, commitments

    def test_state_commitments_are_identical_with_and_without_the_connector(self):
        plain, plain_commitments = self._run(with_gates=False)
        gated, gated_commitments = self._run(with_gates=True)
        self.assertEqual(plain_commitments, gated_commitments)
        self.assertEqual(len(plain.audit.ledger), len(gated.audit.ledger))
        self.assertEqual(
            list(plain.integrity.error_history_window), list(gated.integrity.error_history_window)
        )
        self.assertTrue(gated.audit.verify_integrity())


if __name__ == "__main__":
    unittest.main()
