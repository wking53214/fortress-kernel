# fortress-kernel

Optional containment pack for the governed action gate (`observe-perceive`): a heuristic bounded-slew controller (three modes) with an HMAC-signed audit ledger. In the `lyapunov` and `energy` modes it limits how fast its blending coefficient (the share of the live signal it lets through) may change per call. It does not limit how fast the output itself moves: a jump in the live signal passes straight through, and the `sage` mode has no slew limit (EXECUTED 2026-11-15). It is not a verified controller and it enforces nothing outside its own process.

Status: Alpha, version 1.0.0 (`pyproject.toml`). Last checked 2026-11-15 at commit `f5d15b2`. License: Apache-2.0. Default branch is `main` (checked 2026-11-18; it was `Main` on 2026-11-15, and that branch no longer exists). numpy is the only runtime dependency.

## Role Within ≡TACK

- **What it is.** An optional containment pack: `FortressUnified` in `fortress_unified.py` merges three strategies (`sage`, `lyapunov`, `energy`; default `energy`) behind `FortressConfig.controller_mode`.
- **What it owns.** Its controller state, its integrity, invariant, drift and oscillation checks, and its own audit ledger.
- **What it contributes.** A guard whose blending coefficient has a bounded slew, placed after PERCEIVE and before or around execution, where a consumer chooses to use it.
- **What it does not own.** Policy approval, grants, simulation of futures, execution, or any enforcement of its verdicts. It returns a result; the caller decides whether to halt.
- **Depends on.** numpy. Optionally CNS v4.0.0 for the connector.
- **Depended on by.** `observe-perceive` through its `fortress` extra and `fortress_perceive_adapter.py` (INSPECTED: the adapter and two tests exist there). Whether that path runs in any live setup is UNKNOWN.
- **Verified versus declared.** The adapter wiring exists in code. Nothing here proves the containment holds end to end.
- **Governance and control design.** Containment, not authority. Fail-closed behavior depends on the consuming adapter treating a refusal as a halt; that is observe-perceive's job, not this repo's.

## Scope and exclusions

Not a policy approver, not AUGUR (veto simulation), and not VANGUARD. Mentions of ESN or Lyapunov in retired VANGUARD files are not this code.

## Core implemented capabilities

IMPLEMENTED (tests passed 2026-11-15): `IntegrityLayer` (refuses non-finite error), `InvariantMonitor`, `DriftMonitor`, `MandateLayer` (clamps an action delta; not called by `FortressUnified.process`), `OscillationDetector`, three controllers, and `ImmutableAuditLedger` (HMAC-signed, hash-chained records, verified by `verify_integrity`). `FortressUnified.process` applies only the numeric-safety refusal itself. It builds an `InvariantMonitor` and a `DriftMonitor` and calls neither.

The "Lyapunov" and "energy" names describe heuristics. This repo contains no stability proof (INFERRED from inspection; REPORTED by Phase 0). Do not read the names as a stability or containment guarantee.

Tunables are engineering guesses, not fitted values: `activation_threshold=0.45`, `authority_enter_threshold=0.55`, `authority_exit_threshold=0.35`, `nominal_slew=0.20`, `sensitivity=15.0`, `max_contraction_ratio=0.98`, `fim_beta=0.90`, `recovery_freeze_cycles=8`, `prov_risk_no_sig=0.5`, `rng_seed=42`, and others in `FortressConfig`.

## Layout and interfaces

Single top-level module `fortress_unified.py`, plus the optional `fortress_cns_connector.py` and tests at the repo root. Exposed: `FortressConfig`, `FortressUnified.process(payload, error, live_signal)`, `kernel.audit` (the ledger). Consumed: nothing external.

## Trust model and failure behavior

- **Audit key.** The ledger signs with `audit_key`, or `FORTRESS_AUDIT_KEY`, or else a random per-ledger key. With no key set, `ledger.ephemeral_key` is `True`, a warning is logged, tampering is caught in-process only, and records cannot be verified elsewhere. "Caught" means an edited record fails `verify_integrity`. Deleting records from the end of the ledger, or all of them, still verifies (EXECUTED 2026-11-15). The ledger is held in memory only; this repo writes nothing to disk. `FortressUnified` builds its ledger with no arguments, so the environment variable is the way to supply a key. An empty value counts as unset.
- **Old commit with a hard-coded key.** Commit `4105ccb5` signs with the fixed key `"fortress-key"` (INSPECTED with `git show`). `observe-perceive`'s `fortress` extra still pins that commit (INSPECTED). Anyone using that pin has a publicly known signing key. Moving the pin is an owner action.
- HMAC with a shared key is integrity checking, not authentication of who wrote a record. Hashing is not authorization.
- **Provenance is a label, not a check.** No signature is verified anywhere in this repo. The result says `VERIFIED` whenever the payload metadata has a non-empty `signature` value. Separately, the `lyapunov` and `energy` controllers drop their 0.5 risk penalty whenever the metadata contains the keys `source_id` and `signature`, whatever the values. A caller who adds those two keys can keep the override from engaging on inputs that would otherwise trigger it (EXECUTED 2026-11-15). Treat both as caller-supplied claims.
- **Fixed fallback and silent defaults.** When the override engages, the output is blended toward the constant `50.0`, which is written in the code and is not configurable. Any `controller_mode` other than `sage` or `lyapunov`, including a typo, silently selects `energy`. Thirteen of the 29 `FortressConfig` fields, including `activation_threshold`, are never read by the code (INSPECTED).
- **Failure behavior.** A NaN or infinite error is refused. Other inputs can still fail late: see the connector notes below for float32, huge values and NaN signals, each of which raises after the controller state has been updated.

## Install and quick start

```
pip install -e '.[dev]'
python -m pytest -q
```

The wheel lists `fortress_unified` and `fortress_cns_connector` as modules. No `tests/` folder exists: the tests are `test_*.py` at the repo root.

## Testing and verification

EXECUTED 2026-11-15 (Python 3.13): 82 passed, 1 skipped, 3 subtests passed. The skip is the CNS connector test because CNS was not installed. The README's earlier "48 tests" was stale. This shows the code behaves as tested. It does not show the controller is stable or the containment is sufficient.

## Known limitations

- Thresholds are uncalibrated. Rebuilding this guard per actuator is easy; treat it as a feature, not a product.
- The `4105ccb5` pin issue above.
- No stability analysis. Several validity checks the kernel contains are not called by `process`.
- The `pyproject.toml` description and development-status classifier were corrected on 2026-11-15; previously they said "Production/Stable" and "mandate-driven control".

## 8. Connecting to CNS (optional)

The kernel stands alone: numpy is still its only runtime dependency, nothing imports CNS when the kernel loads, and the kernel tests pass with CNS absent. If CNS is installed, `fortress_cns_connector` expresses the kernel's own verdicts as `cns.gate` results so they can be resolved alongside gates from other repositories. It runs the kernel's own predicates unchanged and never re-implements a threshold.

```
pip install 'fortress-kernel[cns] @ git+https://github.com/wking53214/fortress-kernel.git@main'
```

fortress-kernel is not on a package index, so the extra is installed from git (pin a commit instead of `main` for a reproducible install: use a current commit such as `f5d15b2`, checked 2026-11-15, and never `4105ccb5` or any other commit before `c361569`, because those sign with the hard-coded key) or from a checkout with `pip install '.[cns]'`. CNS needs Python 3.10 or newer.

**The connector's error message still prints an older line.** `CnsNotInstalled` says `pip install 'fortress-kernel[cns] @ git+https://github.com/wking53214/fortress-kernel.git@Main'`. That line fails, because the branch `Main` no longer exists. The line above, ending in `@main`, installs (both EXECUTED 2026-11-18). The older line is repeated here because a test checks that this README contains the message's command word for word. Changing the message is a code change and has not been made.

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

Without CNS installed, the connector's functions raise `CnsNotInstalled` with the install command. Nothing else in the kernel changes. The connector adds its own tests in `test_fortress_cns_independence.py` (run in a subprocess with CNS blocked, never skipped) and `test_fortress_cns_connector.py` (skipped when CNS is absent, unless `FORTRESS_REQUIRE_CNS=1`, which CI's `cns` job sets so a missing CNS fails there).

Maintainer: William N. King.
