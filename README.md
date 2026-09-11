# FORTRESS-KERNEL

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

---

# Core Concept

FORTRESS-KERNEL establishes a controlled boundary around a protected state.

Instead of allowing state to be modified without an explicit control mechanism:

    STATE
      │
      ▼
    UNCONTROLLED MUTATION
      │
      ▼
    NEW STATE

FORTRESS-KERNEL introduces a governed control path:

    STATE
      │
      ▼
    FORTRESS-KERNEL
      │
      ├── validate
      ├── enforce
      ├── compare
      ├── detect drift
      ├── verify invariants
      ├── evaluate mandate
      └── record audit state
      │
      ▼
    AUTHORIZED STATE

The kernel therefore acts as a control boundary between a stateful system and the changes permitted to that system.

---

# Architectural Principle

The fundamental capability of FORTRESS-KERNEL is not any particular control algorithm.

It is the ability to place multiple explicit control mechanisms behind a common enforcement boundary.

Conceptually:

    INPUT STATE
        │
        ▼
    CONTROL POLICY
        │
        ▼
    CONTROL KERNEL
        │
        ├── CONTROL MODE A
        ├── CONTROL MODE B
        └── CONTROL MODE C
        │
        ▼
    INTEGRITY / INVARIANT CHECKS
        │
        ▼
    AUTHORIZED RESULT

This permits different control strategies to operate within a common framework without requiring the downstream system to understand the internal implementation of each strategy.

---

# Multi-Mode Control

The kernel unifies three control strategies behind a common interface.

The strategies represent different ways of determining how a protected state should respond to an input or deviation.

The important architectural property is the common control surface.

Rather than exposing three unrelated implementations:

    CONTROL A
    CONTROL B
    CONTROL C

FORTRESS-KERNEL provides:

    ┌──────────────────────────────┐
    │       FORTRESS-KERNEL        │
    │                              │
    │   ┌──────┐ ┌──────┐ ┌──────┐ │
    │   │Mode A│ │Mode B│ │Mode C│ │
    │   └──────┘ └──────┘ └──────┘ │
    │                              │
    └──────────────┬───────────────┘
                   │
                   ▼
             CONTROL RESULT

This allows the control mechanism to be changed without changing the fundamental interface through which the protected state is governed.

---

# Integrity

Integrity is a core concern of the kernel.

A control decision is not meaningful if the state against which the decision is made can be silently altered.

FORTRESS-KERNEL therefore incorporates integrity-oriented mechanisms into the control path.

Conceptually:

    OBSERVED STATE
          │
          ▼
       INTEGRITY
          │
          ├── valid
          │
          └── compromised / inconsistent
          │
          ▼
       CONTROL

Integrity is therefore treated as a prerequisite to trustworthy control rather than as an unrelated logging feature.

---

# Invariants

FORTRESS-KERNEL supports explicit invariant enforcement.

An invariant represents a condition that must remain true for the protected system to remain within its defined operating constraints.

The conceptual relationship is:

    STATE
      │
      ▼
    INVARIANTS
      │
      ├── satisfied
      │
      └── violated
      │
      ▼
    CONTROL RESPONSE

This allows the kernel to distinguish between:

    "A state changed"

and:

    "A state changed in a way that violates a condition that must remain true."

That distinction is fundamental to controlled state evolution.

---

# Drift

The kernel also incorporates drift-oriented reasoning.

A state can remain technically valid while nevertheless moving progressively away from its intended or established operating condition.

The architectural distinction is:

    VALID STATE

versus:

    ACCEPTABLE STATE

and:

    CURRENT STATE

versus:

    EXPECTED / ESTABLISHED STATE

Drift monitoring allows the system to identify changes that may not constitute an immediate invariant violation but nevertheless represent meaningful deviation.

---

# Mandate

FORTRESS-KERNEL includes the concept of an explicit mandate governing the control operation.

A mandate establishes the authority or operating constraint under which a control action is permitted.

Conceptually:

    REQUEST
       │
       ▼
    MANDATE
       │
       ├── permitted
       │
       └── not permitted
       │
       ▼
    CONTROL ACTION

This separates:

    "The system can perform this action"

from:

    "The system is authorized to perform this action."

The distinction becomes important when the kernel is incorporated into larger governed systems.

---

# Control Boundary

FORTRESS-KERNEL can be placed at a boundary where state-changing operations must pass through a controlled mechanism.

For example:

    ┌──────────────────┐
    │ UPSTREAM SYSTEM  │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ FORTRESS-KERNEL  │
    │                  │
    │ integrity        │
    │ invariants       │
    │ mandate          │
    │ drift            │
    │ control modes    │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ DOWNSTREAM STATE │
    └──────────────────┘

This allows the kernel to serve as an enforcement point without requiring the upstream or downstream system to implement the complete control architecture itself.

---

# Auditability

Control operations should be reconstructable.

FORTRESS-KERNEL therefore maintains audit-oriented information associated with control activity.

The purpose is to preserve information about:

- what state was presented;
- what control mechanism was applied;
- what conditions were evaluated;
- whether constraints were satisfied;
- what result was produced;
- and what state followed.

The kernel therefore treats control as an observable operation rather than an opaque function call.

## State Provenance

Each committed audit state receives a deterministic `state_commitment`. The commitment
canonically serializes the relevant FORTRESS state and includes the prior commitment,
creating a logical chain across transitions. The existing HMAC remains the mechanism
for authenticating audit records; the commitment is an identifier and tamper-evident
link, not encryption, non-repudiation, or protection against a compromised audit key.

An optional `OscillationDetector` can report repeated normalized controller-result
observations across a kernel instance. It is resettable and instance-scoped, and its
signal is advisory: repeated output is not necessarily mathematical oscillation and
does not authorize, reject, or alter a control result.


---

# Deterministic Control

The kernel is designed around explicit and reproducible control logic.

Given the same:

- input state;
- control parameters;
- mandate;
- invariant configuration;
- and implementation,

the control path should produce a reproducible result.

This makes the system suitable for environments where control behavior needs to be:

- tested;
- inspected;
- reproduced;
- compared;
- and audited.

---

# Domain Independence

FORTRESS-KERNEL is not inherently tied to a particular industry.

The kernel's underlying concerns are structural:

- protected state;
- control policy;
- integrity;
- invariants;
- mandate;
- drift;
- control strategy;
- and auditability.

Those concerns can arise in many environments.

Potential application domains could include:

- autonomous systems;
- industrial control;
- software infrastructure;
- cybersecurity;
- communications;
- transportation;
- financial systems;
- AI systems;
- safety-critical systems;
- or other environments requiring controlled state transitions.

These are architectural examples rather than claims that the repository currently implements each of those applications.

---

# Current Implementation

The current repository provides a concrete implementation of the kernel using its unified control architecture.

The implementation demonstrates:

- multiple control strategies;
- a common control interface;
- state management;
- integrity-related checks;
- invariant handling;
- drift-related controls;
- mandate-related controls;
- and audit-oriented state.

The current implementation should therefore be understood as the **representative implementation of the kernel**, rather than as a domain-specific product.

---

# Relationship to Other Systems

FORTRESS-KERNEL is not exclusively designed to attach to a particular neighboring repository.

It does not fundamentally depend upon one specific external system to define its purpose.

Its architectural role is that of a reusable kernel that can be incorporated into systems requiring its control primitives.

Conceptually:

    SYSTEM A ──┐
               │
    SYSTEM B ──┼──► FORTRESS-KERNEL
               │
    SYSTEM C ──┘

provided that the surrounding system supplies the appropriate interface and operating context.

The repository should therefore be regarded as **composable rather than single-repository-specific**.

---

# Relationship to Governance

FORTRESS-KERNEL can provide an enforcement primitive within a larger governance architecture.

The distinction is:

    GOVERNANCE
        │
        │ defines what must be true
        ▼
    FORTRESS-KERNEL
        │
        │ enforces / evaluates
        ▼
    PROTECTED STATE

The kernel therefore does not need to contain the entire governance system.

It can instead act as the mechanism through which defined constraints are enforced against state.

This makes it suitable as a lower-level component within a larger governed architecture.

---

# Architectural Separation

FORTRESS-KERNEL separates several concerns that are often collapsed into a single control function.

Conceptually:

    ┌───────────────────────────────┐
    │            POLICY             │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │           MANDATE             │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │           CONTROL             │
    │                               │
    │       multiple modes          │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │          INVARIANTS            │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │           INTEGRITY            │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │             STATE              │
    └───────────────────────────────┘

This separation makes the kernel easier to reason about and test independently.

---

# What FORTRESS-KERNEL Is Not

FORTRESS-KERNEL is not:

- a complete enterprise governance platform;
- a general-purpose authorization server;
- an industry-specific safety system;
- a generic database;
- a monitoring platform;
- or a replacement for the larger system in which it may be deployed.

It is a **control kernel**.

Its purpose is to provide reusable mechanisms for controlled state evolution.

---

# Design Principles

## Explicit Control

State changes should pass through identifiable control logic.

## Multiple Control Strategies

Different control approaches should be able to operate behind a common interface.

## Integrity Before Trust

The kernel should not blindly operate on state whose integrity cannot be established.

## Invariants

Conditions that must remain true should be explicitly represented and evaluated.

## Mandate Continuity

Capability and authority should remain conceptually distinct.

## Drift Awareness

Gradual deviation should be detectable even when absolute constraints have not yet failed.

## Auditability

Control decisions should leave an inspectable representation of what occurred.

## Domain Independence

The kernel should not require a particular industry or application domain.

## Composability

The kernel should be capable of being incorporated into different surrounding architectures rather than being permanently coupled to one repository.

---

# Architectural Model

The complete conceptual flow is:

    ┌─────────────────────┐
    │     INPUT STATE     │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │      MANDATE        │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │      INTEGRITY      │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │     INVARIANTS      │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │       DRIFT         │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │   CONTROL ENGINE    │
    │                     │
    │  ┌───┐ ┌───┐ ┌───┐ │
    │  │ A │ │ B │ │ C │ │
    │  └───┘ └───┘ └───┘ │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │    CONTROL RESULT   │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │       AUDIT         │
    └─────────────────────┘

---

# Current Status

FORTRESS-KERNEL is a reusable control-kernel implementation demonstrating how multiple control strategies can be placed behind a common enforcement boundary while incorporating integrity, invariant, mandate, drift, and audit considerations.

Its current implementation is the **representative example of the architecture in operation**.

The architecture itself is not restricted to the current example, a particular industry, or a particular neighboring repository.

---

# Central Proposition

> **A protected system state should not be changed merely because an operation is technically possible. A control kernel can establish the conditions under which state may change, evaluate those conditions through multiple control strategies, preserve integrity and invariants, account for mandate and drift, and produce an auditable result.**