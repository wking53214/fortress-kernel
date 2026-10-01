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

Proprietary. Copyright (c) 2026 William N. King. All rights reserved. See LICENSE.
