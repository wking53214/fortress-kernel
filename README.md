# FORTRESS-KERNEL

**Role in the governed action stack:** OPTIONAL containment pack for [observe-perceive](https://github.com/wking53214/observe-perceive) — bounds actuator slew/target and audit chain of interventions. Not a standalone product. Distinct from [AUGUR](https://github.com/wking53214/AUGUR) (veto-only simulation screen).

```text
Live path: Admission → OBSERVE/Keys → Locks → PERCEIVE → Decision → Conservation → Execution → Custody
Optional: AUGUR · fortress-kernel · CCC
```

---

> **Unfrozen 2026-09-11.** fortress-kernel is an optional containment
> pack for the governed action gate in
> [observe-perceive](https://github.com/wking53214/observe-perceive), not a
> product on its own. It bounds the slew and target of an automated actuator
> and keeps an audit chain of interventions. It passes its own suite with no
> sibling present (48 tests) and is consumed by the gate only when
> `fortress_controller` is set.
>
> The 90-day freeze set on 2026-09-08 is lifted early, by the owner's
> decision. It was set on the evidence available that day, which
> predates two things that change the picture: the private `CNS`
> package, one measured schema that the library's repositories join
> on rather than re-typing, and `ghost_tools`' kernel scan, which
> measures duplication and drift against it. Neither existed when the
> freeze was written.
>
> The commercial reading above is **not** superseded. Everything the
> audit established about this repo still holds, including anything it
> says is missing; lifting the freeze removes a restriction on effort,
> not a finding. See
> `docs/audit/COMMERCIAL_RED_TEAM_2026-09-08.md` in observe-perceive, Parts 18 and 35,
> for what the freeze was based on.

## Deterministic Multi-Mode Control and Integrity Kernel

FORTRESS-KERNEL is a domain-independent control kernel designed to enforce explicit constraints over a protected state while preserving integrity, invariants, drift awareness, mandate continuity, and auditable state transitions.

The current implementation demonstrates these capabilities through a unified kernel that combines multiple control strategies behind a common interface.

The current implementation is a representative example of how the kernel functions. It does not define the architectural limits or intended application domain of FORTRESS-KERNEL.

See the remainder of this document for control modes, integrity, invariants, drift, mandate, auditability, and design principles.

## Install and test

```bash
pip install -e ".[test]"
pytest
```

## Central proposition

> A protected system state should not be changed merely because an operation is technically possible. A control kernel can establish the conditions under which state may change, evaluate those conditions through multiple control strategies, preserve integrity and invariants, account for mandate and drift, and produce an auditable result.
