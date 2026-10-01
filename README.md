# fortress-kernel

Optional **containment pack** for the governed action gate: unified control (SAGE-K / Lyapunov / Energy) with bounded slew. **Default branch: `Main`** (capital M). numpy required.

## 1. Pipeline Position & Role

**OPTIONAL CONTAINMENT** after/beside PERCEIVE, before or around execution. Wired from [`observe-perceive`](https://github.com/wking53214/observe-perceive) extra `fortress` (`fortress_perceive_adapter.py`). Not a standalone product. Distinct from AUGUR (veto simulation).

## 2. Full System Scope & Architectural Depth

`fortress_unified.py` merges three strategies behind `FortressConfig.controller_mode`: `"sage"` | `"lyapunov"` | `"energy"` (default energy).

Uncalibrated / hardcoded tunables (honest list, not exhaustive): `activation_threshold=0.45`, `authority_enter_threshold=0.55`, `authority_exit_threshold=0.35`, `nominal_slew=0.20`, `sensitivity=15.0`, `max_contraction_ratio=0.98`, `fim_beta=0.90`, `recovery_freeze_cycles=8`, `prov_risk_no_sig=0.5`, divergence caps `0.45` / scale `25.0`, buffer lengths 10/16, `rng_seed=42`.

HMAC appears in the unified kernel; numpy state vectors are the actual control substrate.

## 3. What It Does NOT Do / Non-Goals

- Does not approve policy or issue grants.
- Does not simulate futures (AUGUR).
- Docstrings mentioning ESN/Lyapunov in **VANGUARD** are not this code; do not confuse the retired VANGUARD files with this package.

## 4. Brutally Honest Current Status & Gaps

Commercial red team: **FEATURE** (a well-made guard, not a market). Easy to rebuild per actuator. 48 tests. Unfrozen 2026-09-11. Thresholds are engineering guesses, not fitted controllers. Branch name `Main` breaks naive `git clone -b main`.

## 5. Core Invariants & Guarantees

Bounded slew/target when the controller is actually invoked. Audit chain of interventions inside the module. Fail-closed only if the adapter treats containment refusal as halt — that is observe-perceive's job.

## 6. Inputs, Outputs & Type Contracts

`FortressConfig` + unified orchestrator in `fortress_unified.py`. Pin: `fortress-kernel @ git+…@4105ccb5`.

## 7. Stack Integration Topology

```text
observe-perceive extra `fortress` → fortress_perceive_adapter → fortress_unified
AUGUR is NOT this repo
VANGUARD is retired specimens in TOUCHSTONE
```

## 8. Connecting to CNS (optional)

The kernel stands alone: numpy is still its only runtime dependency, nothing imports CNS when the kernel loads, and the 48 kernel tests pass with CNS absent. If CNS is installed, `fortress_cns_connector` expresses the kernel's own verdicts as `cns.gate` results so they can be resolved alongside gates from other repositories. It runs the kernel's own predicates unchanged and never re-implements a threshold.

```
pip install 'fortress-kernel[cns] @ git+https://github.com/wking53214/fortress-kernel.git@Main'
```

fortress-kernel is not on a package index, so the extra is installed from git (pin a commit instead of `Main` for a reproducible install, as in section 6) or from a checkout with `pip install '.[cns]'`. CNS needs Python 3.10 or newer.

```python
from fortress_cns_connector import NumericSafetyGate, InvariantGate, AuditChainGate
from cns.gate import resolve

admit = NumericSafetyGate().check({"error": error})         # ALPHA, before process()
if admit.blocking():
    raise SystemExit(admit.reason)                           # process() is never called
result = fortress.process(payload, error, live_signal)
ran = [
    InvariantGate().check({"state": result["output"], "distortion": result["distortion"],
                           "error": error, "volatility": volatility}),   # OMEGA
    AuditChainGate().check(fortress.audit),                              # OMEGA
]
resolve([admit, *ran])    # PASS, RETRY or TERMINAL_BREACH, fail-closed
```

| Kernel decision | CNS position | CNS outcome | Verdict is bound to |
|---|---|---|---|
| `IntegrityLayer.analyze` refuses a NaN or infinite error (`numeric_safety`) | `ALPHA`: it is the first line of `process()`, before the controller or the audit run | refused: `TERMINAL_BREACH`; otherwise `PASS` | `{"error": e}` |
| `MandateLayer.enforce` on a proposed action delta (`mandate`) | `ALPHA`: judges the action before it is applied | delta unchanged: `PASS`; clamped: `RETRY`, with the kernel's clamped delta in `reason` | `{"action": {"delta": d}, "current_kpi", "target_kpi", "volatility"}` |
| `InvariantMonitor.check` (`invariants`) | `OMEGA`: judges state, distortion, error and volatility a run produced | any violation: `TERMINAL_BREACH`; none: `PASS` | `{"state", "distortion", "error", "volatility"}` |
| `ImmutableAuditLedger.verify_integrity` (`audit_chain`) | `OMEGA`: judges the ledger the kernel produced | False or raising: `TERMINAL_BREACH`; True: `PASS` | `{"records": ledger.ledger}`, never the audit key |

`cns_chain()` returns a `cns.gate.GateChain` with the two `ALPHA` gates in `alpha` and the two `OMEGA` gates in `omega`. The kernel has both ends, but `FortressUnified.process` applies only the numeric-safety refusal itself; it constructs an `InvariantMonitor` and a `DriftMonitor` and calls neither, and it has no `MandateLayer`. The connector does not wire them in.

`volatility` is the volatility of this run. `process()` does not return the one its `IntegrityLayer` computed, so pass the one you measured: a hard-coded `0.0` would make `VOLATILITY_SPIKE` unreachable and bind the verdict to a reading the run did not produce.

Things to know:

- **A `PASS` from `numeric_safety` is narrow.** It judges the error reading, the first thing `process()` checks, and nothing else. It does not promise that `process()` succeeds: a `numpy.float32` error passes and `process()` then raises `TypeError` from the ledger, an error of `1e308` passes and `process()` raises `OverflowError` in the controller, and a NaN `live_signal` raises `ValueError` from the ledger, each after the controller has already updated its state.
- **Fail closed on non-finite numbers.** `InvariantMonitor.check` returns `[]` for NaN and `MandateLayer.enforce` passes a NaN delta through, so the kernel alone would read them as fine. The connector reports any NaN or infinite input to those two gates as `TERMINAL_BREACH`. The kernel's functions are unchanged.
- **`invariants` mirrors the monitor, asymmetry included.** `InvariantMonitor.check` bounds `state` on both sides but `error`, `distortion` and `volatility` from above only (`error > 20.0`, no `abs()`), so a large negative error is not a `MODEL_FAILURE` and the gate passes it, as the kernel does. The gate reports what the kernel's predicate says and does not widen it; a consumer that wants a symmetric bound has to add one.
- **A clamp as `RETRY` is the connector's inference.** The kernel never rejects a clamped action: `enforce` applies the clamp and the action goes on. The connector reports the clamp as `RETRY`, which blocks, so a connected consumer is stricter than the kernel here. The kernel's own clamped delta is in `reason` for a consumer that would rather accept it.
- **Digests are stable.** Numpy scalars are turned into plain numbers before hashing, so a digest does not depend on the numpy version. A non-finite number, which CNS cannot hash, is digested as `{"nonfinite": "nan" | "inf" | "-inf"}` and the verdict stays bound. Content CNS cannot describe at all gives an unbound `TERMINAL_BREACH` (empty `subject_digest`, named by `cns.gate.unbound`) and never an exception or a `PASS`. For a tampered ledger that is a record holding a set, bytes or another object, a mapping with a non-string key, a lone surrogate, an integer of more than 4300 digits, a cycle, nesting deeper than CNS can recurse (a few hundred levels, which the kernel itself still accepts), or a ledger that has lost its `ledger` list.
- **Three kernel outputs are not mapped.** `DriftMonitor` returns an advisory `(is_drifting, drift)`, `OscillationDetector` only feeds the `oscillation_detected` field of the result and the audit record, and the `VERIFIED` / `UNVERIFIED` label on the result is set from whether the payload carries a signature value. The kernel defines no consequence for any of them, so any outcome would be invented.

Without CNS installed, the connector's functions raise `CnsNotInstalled` with the install command. Nothing else in the kernel changes. The connector adds its own tests in `test_fortress_cns_independence.py` (run in a subprocess with CNS blocked, never skipped) and `test_fortress_cns_connector.py` (skipped when CNS is absent).

Proprietary. Copyright (c) 2026 William N. King. All rights reserved. See LICENSE.
