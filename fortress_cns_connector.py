"""Optional connector to CNS (``cns.gate``).

fortress-kernel is independent. It has no runtime dependency on CNS (numpy
stays its only one), imports nothing from CNS when it loads, and its whole
suite passes with CNS absent. This module is the one place that knows CNS
exists, and it asks for CNS only when one of its functions is called. Without
CNS installed those calls raise :class:`CnsNotInstalled` with the install
command; nothing else in the kernel is affected.

What connecting means
---------------------
The kernel makes four real decisions, none of them as a shared verdict type:

* ``IntegrityLayer.analyze`` refuses a NaN or infinite error reading by
  raising ``ValueError`` ("Numeric Safety Exception"). It is the first line of
  ``FortressUnified.process``: the controller and the audit append never run.
* ``MandateLayer.enforce`` clamps a proposed action delta to a speed limit and
  a target window, in place, and returns the clamped action.
* ``InvariantMonitor.check`` returns the list of hard bounds a state violates
  (empty means none).
* ``ImmutableAuditLedger.verify_integrity`` returns whether the HMAC and
  commitment chain is intact.

This module runs those unchanged and expresses each answer as a bound
``cns.gate.GateResult``, so a consumer that speaks CNS can resolve them with
gates from other repositories. It never re-implements a threshold: the
predicate is always the kernel's own.

The mapping, and why
--------------------
==================  ========  ==============================================
gate                position  CNS outcome
==================  ========  ==============================================
``numeric_safety``  ALPHA     refused (ValueError) -> ``TERMINAL_BREACH``;
                              else ``PASS``. It judges the error reading
                              before the controller runs, and the kernel
                              models no repair for it.
``mandate``         ALPHA     delta unchanged -> ``PASS``; clamped ->
                              ``RETRY`` (the kernel's own clamped delta is
                              the repair, carried in ``reason``); cannot be
                              decided -> ``TERMINAL_BREACH``. It judges a
                              proposed action before it is applied.
``invariants``      OMEGA     any violation -> ``TERMINAL_BREACH`` (a hard
                              bound, no repair modelled); none -> ``PASS``.
                              It judges state, distortion, error and
                              volatility as a run produced them.
``audit_chain``     OMEGA     ``verify_integrity()`` False or raising ->
                              ``TERMINAL_BREACH``; True -> ``PASS``. It
                              judges the ledger the kernel produced.
==================  ========  ==============================================

Fail closed
-----------
Two of the kernel's checks are silent about non-finite numbers:
``InvariantMonitor.check`` returns ``[]`` for NaN (every comparison is False)
and ``MandateLayer.enforce`` passes a NaN delta through untouched. The kernel
itself calls non-finite input unsafe (``IntegrityLayer`` refuses it and the
ledger will not commit it), so the connector never reads "the kernel found
nothing" as ``PASS`` when an input is NaN or infinite: that is
``TERMINAL_BREACH`` with a reason. The native functions are not changed.

What each verdict is bound to
-----------------------------
``subject`` labels what was judged (a per-gate default, overridable) and
``subject_digest`` is ``cns.gate.subject_digest`` over exactly the content the
kernel's predicate read, nothing more:

==================  ===================================================
gate                digest content
==================  ===================================================
``numeric_safety``  ``{"error": e}``
``mandate``         ``{"action": {"delta": d}, "current_kpi": c,
                    "target_kpi": t, "volatility": v}``
``invariants``      ``{"state": s, "distortion": d, "error": e,
                    "volatility": v}``
``audit_chain``     ``{"records": ledger.ledger}``, which never includes
                    the audit key
==================  ===================================================

Numbers are normalised first: numpy scalars and ``bool`` become plain ``int``
or ``float``, so a digest does not depend on the numpy version (``repr`` of a
``numpy.float64`` differs between numpy 1 and 2). CNS refuses NaN and
infinities, but the kernel's real inputs can be non-finite, so a non-finite
scalar is digested as ``{"nonfinite": "nan" | "inf" | "-inf"}`` and the
verdict stays bound. Content CNS cannot describe at all yields an *unbound*
``TERMINAL_BREACH``: ``subject_digest`` is empty, ``cns.gate.unbound`` names it,
and it binds to nothing. For a tampered ledger that means any record holding a
set, bytes or another object, a mapping with a non-string key, a lone
surrogate, an integer of more than 4300 digits, a cycle, nesting deeper than
CNS can recurse (a few hundred levels, which the kernel itself still accepts),
or a ledger that has lost its ``ledger`` list. The gate never raises for
tampered content and never returns ``PASS`` for it: judging a tampered ledger
is what the audit gate is for.

What a verdict does not say
---------------------------
A ``PASS`` from ``numeric_safety`` is about the error reading only, the first
thing ``process`` checks. It does not promise that ``process`` succeeds: a
``numpy.float32`` error passes the gate and ``process`` then raises
``TypeError`` from the ledger, an error of ``1e308`` passes and ``process``
raises ``OverflowError`` in the controller, and a NaN ``live_signal`` raises
``ValueError`` from the ledger, each after the controller has already updated
its state. ``InvariantMonitor`` bounds ``state`` on both sides but ``error``,
``distortion`` and ``volatility`` from above only (``error > 20.0``, no
``abs()``), so the invariants gate passes a large negative error, exactly as
the kernel does. The kernel does not reject a clamped action either:
``enforce`` applies the clamp and the action goes on, so reporting the clamp as
a blocking ``RETRY`` is the connector's inference, and stricter than the
kernel.

The kernel has both ends, but ``FortressUnified.process`` applies only the
numeric-safety refusal itself: it constructs an ``InvariantMonitor`` and a
``DriftMonitor`` and calls neither, and it has no ``MandateLayer``. The
connector does not wire them in. Three more kernel outputs are left out on
purpose, because the kernel defines no consequence for them and any outcome
would be invented: ``DriftMonitor`` (an advisory ``(is_drifting, drift)``),
``OscillationDetector`` (``process`` records ``oscillation_detected`` and does
nothing else with it) and the ``VERIFIED`` / ``UNVERIFIED`` label on the result
(set from whether the payload carries a signature value; nothing acts on it).

fortress-kernel is not on a package index, so the extra is installed from git
or from a checkout (``pip install '.[cns]'``); see ``INSTALL_HINT``.
"""

from __future__ import annotations

import importlib
import math
import numbers
from types import ModuleType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from fortress_unified import (
    FortressConfig,
    ImmutableAuditLedger,
    IntegrityLayer,
    InvariantMonitor,
    MandateLayer,
    Payload,
)

__all__ = [
    "AuditChainGate",
    "CnsNotInstalled",
    "InvariantGate",
    "MandateGate",
    "NumericSafetyGate",
    "cns_available",
    "cns_chain",
    "to_cns_result",
]

# Not a bare index name: fortress-kernel is not on any index, and installing a
# bare name from one is a dependency-confusion exposure. A direct reference to
# the repository resolves, and so does ``pip install '.[cns]'`` from a checkout.
INSTALL_HINT = (
    "pip install 'fortress-kernel[cns] @ "
    "git+https://github.com/wking53214/fortress-kernel.git@Main'"
)

#: gate name -> (``cns.gate.GatePosition`` member name, default ``subject``).
_GATES: Dict[str, Tuple[str, str]] = {
    "numeric_safety": ("ALPHA", "error"),
    "mandate": ("ALPHA", "action"),
    "invariants": ("OMEGA", "state"),
    "audit_chain": ("OMEGA", "audit_ledger"),
}


class CnsNotInstalled(ImportError):
    """Raised by this module's functions when ``cns`` cannot be imported."""


def _cns_gate() -> ModuleType:
    """Import ``cns.gate`` on demand, or say exactly what is missing.

    An absent CNS is an ``ImportError``, but a CNS that is present and unusable
    (a release without ``cns.gate``, a Python too old for it) can raise
    anything while it imports. Every such failure means the same here: the
    contract cannot be used, so it is reported as :class:`CnsNotInstalled` with
    the underlying error named.
    """
    try:
        return importlib.import_module("cns.gate")
    except Exception as exc:
        raise CnsNotInstalled(
            "fortress_cns_connector needs the CNS package (cns.gate), and it could "
            f"not be imported ({type(exc).__name__}: {exc}). Install it with: "
            f"{INSTALL_HINT} (CNS needs Python 3.10 or newer). fortress-kernel "
            "itself works without it."
        ) from exc


def cns_available() -> bool:
    """Whether the CNS gate contract can be imported in this environment."""
    try:
        _cns_gate()
    except CnsNotInstalled:
        return False
    return True


# ---------------------------------------------------------------------------
# Translation: the kernel's verdict -> a bound cns.gate.GateResult
# ---------------------------------------------------------------------------

def _bind(cns: ModuleType, content: Mapping[str, Any]) -> str:
    """``cns.gate.subject_digest(content)``, or ``TypeError`` for content CNS cannot describe.

    CNS refuses an unsupported type with ``TypeError`` but trips over other
    shapes with other errors: a non-string mapping key is a ``KeyError``, a lone
    surrogate a ``UnicodeEncodeError``, an integer of more than 4300 digits a
    ``ValueError`` and nesting past the recursion limit a ``RecursionError``.
    What a tamper can change is exactly what a digest has to survive, so every
    one of them is the same answer here, with the original error as the cause.
    """
    try:
        return cns.subject_digest(content)
    except TypeError:
        raise
    except Exception as exc:
        raise TypeError(
            f"cannot bind a verdict to this content ({type(exc).__name__})"
        ) from exc


def to_cns_result(
    gate: str,
    *,
    passed: bool,
    content: Mapping[str, Any],
    reason: str = "",
    retryable: bool = False,
    subject: Optional[str] = None,
) -> Any:
    """Translate one kernel verdict on ``content`` into a ``cns.gate.GateResult``.

    ``gate`` is one of the four gate names above and fixes the position.
    ``passed`` maps to ``PASS``; a failure maps to ``RETRY`` when the kernel
    models a repair (``retryable``) and to ``TERMINAL_BREACH`` otherwise. The
    result is bound: ``subject_digest`` is ``cns.gate.subject_digest(content)``.
    Content CNS cannot describe, whatever the reason, gives an unbound
    ``TERMINAL_BREACH``, never a ``PASS`` and never an exception.
    """
    cns = _cns_gate()
    if gate not in _GATES:
        raise ValueError(f"unknown fortress gate {gate!r}; expected one of {sorted(_GATES)}")
    end, default_subject = _GATES[gate]
    if passed:
        outcome = cns.GateOutcome.PASS
    elif retryable:
        outcome = cns.GateOutcome.RETRY
    else:
        outcome = cns.GateOutcome.TERMINAL_BREACH
    try:
        digest = _bind(cns, content)
    except TypeError as exc:
        digest = ""
        outcome = cns.GateOutcome.TERMINAL_BREACH
        reason = f"{reason}; " if reason else ""
        reason += (
            "unbound: judged content cannot be canonicalised "
            f"({type(exc.__cause__ or exc).__name__})"
        )
    return cns.GateResult(
        gate=gate,
        position=getattr(cns.GatePosition, end),
        outcome=outcome,
        reason=reason,
        subject=default_subject if subject is None else subject,
        subject_digest=digest,
    )


# ---------------------------------------------------------------------------
# Normalising what the kernel's predicates read
# ---------------------------------------------------------------------------

def _mapping(gate: str, candidate: object, keys: Sequence[str]) -> Mapping[str, Any]:
    if not isinstance(candidate, Mapping):
        raise TypeError(
            f"{gate} judges a mapping with keys {list(keys)}; got {type(candidate).__name__}"
        )
    missing = [key for key in keys if key not in candidate]
    if missing:
        raise ValueError(f"{gate} candidate is missing {missing}")
    return candidate


def _real(label: str, value: object) -> Any:
    """A plain ``int`` or ``float`` for any real number, numpy scalars included."""
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    raise TypeError(f"{label} must be a real number; got {type(value).__name__}")


def _show(value: Any) -> str:
    """``repr`` that cannot raise on a huge int (CPython refuses more than 4300 digits)."""
    try:
        return repr(value)
    except ValueError:
        return f"<integer of {value.bit_length()} bits>"


def _finite(value: Any) -> bool:
    # An int is always finite; math.isfinite would overflow on a huge one.
    return isinstance(value, int) or math.isfinite(value)


def _scalar(value: Any) -> Any:
    """A digest-safe scalar: CNS refuses NaN and infinities, the kernel's inputs may be them."""
    if _finite(value):
        return value
    return {"nonfinite": "nan" if value != value else ("inf" if value > 0 else "-inf")}


class _Undescribable:
    """Stands in for ledger content that could not even be read; CNS refuses it."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<undescribable>"


def _plain(value: Any) -> Any:
    """Plain-Python rendering of a ledger value, so a digest is stable.

    ``numpy.float64`` is a ``float`` subclass whose ``repr`` is
    ``np.float64(1.5)`` on numpy 2; ``cns.gate.subject_digest`` renders with
    ``repr``. Anything CNS could not describe is left as it is, for CNS to refuse.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

class _FortressGate:
    """Shared shape of the four gates: ``name``, ``position``, ``check``."""

    name: str = ""

    def __init__(self, subject: Optional[str] = None) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        if subject is not None and not subject:
            raise ValueError("subject must be a non-empty label")
        self._subject = subject

    @property
    def position(self) -> Any:
        return getattr(_cns_gate().GatePosition, _GATES[self.name][0])

    def _normalize(self, candidate: object) -> Dict[str, Any]:
        raise NotImplementedError

    def _content(self, values: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def _decide(self, values: Dict[str, Any]) -> Tuple[bool, bool, str]:
        """(passed, retryable, reason), from the kernel's own predicate."""
        raise NotImplementedError

    def digest(self, candidate: object) -> str:
        """The digest a verdict on ``candidate`` carries, for ``GateResult.binds``.

        Raises ``TypeError`` for any content CNS cannot describe, as
        ``cns.gate.subject_digest`` does for an unsupported type.
        """
        return _bind(_cns_gate(), self._content(self._normalize(candidate)))

    def check(self, candidate: object) -> Any:
        values = self._normalize(candidate)
        passed, retryable, reason = self._decide(values)
        return to_cns_result(
            self.name,
            passed=passed,
            retryable=retryable,
            reason=reason,
            content=self._content(values),
            subject=self._subject,
        )


class NumericSafetyGate(_FortressGate):
    """ALPHA. The kernel's refusal of a NaN or infinite error reading.

    Candidate: ``{"error": <real number>}``. Runs ``IntegrityLayer.analyze`` on
    a throwaway layer, so the live layer's history is never touched.
    """

    name = "numeric_safety"

    def _normalize(self, candidate: object) -> Dict[str, Any]:
        found = _mapping(self.name, candidate, ("error",))
        return {"error": _real("error", found["error"])}

    def _content(self, values: Dict[str, Any]) -> Dict[str, Any]:
        return {"error": _scalar(values["error"])}

    def _decide(self, values: Dict[str, Any]) -> Tuple[bool, bool, str]:
        try:
            IntegrityLayer(FortressConfig()).analyze(Payload(""), values["error"])
        except ValueError as exc:
            return False, False, str(exc)
        except OverflowError as exc:  # an int too large for the kernel's float maths
            return False, False, f"OverflowError: {exc}"
        return True, False, ""


class MandateGate(_FortressGate):
    """ALPHA. The kernel's mandate on a proposed action delta.

    Candidate: ``{"action": {"delta": d}, "current_kpi": c, "target_kpi": t,
    "volatility": v}``, the arguments of ``MandateLayer.enforce``. The action
    is never mutated: enforcement runs on a copy. A missing ``delta`` is read
    as ``0.0``, as the kernel reads it.
    """

    name = "mandate"
    _KEYS = ("action", "current_kpi", "target_kpi", "volatility")

    def _normalize(self, candidate: object) -> Dict[str, Any]:
        found = _mapping(self.name, candidate, self._KEYS)
        action = found["action"]
        if not isinstance(action, Mapping):
            raise TypeError(f"action must be a mapping; got {type(action).__name__}")
        return {
            "delta": _real("action.delta", action.get("delta", 0.0)),
            "current_kpi": _real("current_kpi", found["current_kpi"]),
            "target_kpi": _real("target_kpi", found["target_kpi"]),
            "volatility": _real("volatility", found["volatility"]),
        }

    def _content(self, values: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "action": {"delta": _scalar(values["delta"])},
            "current_kpi": _scalar(values["current_kpi"]),
            "target_kpi": _scalar(values["target_kpi"]),
            "volatility": _scalar(values["volatility"]),
        }

    def _decide(self, values: Dict[str, Any]) -> Tuple[bool, bool, str]:
        bad = [key for key, item in values.items() if not _finite(item)]
        if bad:
            names = ", ".join(bad)
            return False, False, f"non-finite input ({names}): the mandate cannot be decided"
        requested = values["delta"]
        try:
            enforced = MandateLayer.enforce(
                {"delta": requested},
                values["current_kpi"],
                values["target_kpi"],
                values["volatility"],
            )["delta"]
        except ArithmeticError as exc:
            return False, False, f"{type(exc).__name__}: {exc}; the mandate cannot be decided"
        if not _finite(enforced):
            return False, False, (
                f"enforced delta {_show(enforced)} is not finite; the mandate cannot be decided"
            )
        if enforced == requested:
            return True, False, ""
        return False, True, (
            f"action delta {_show(requested)} is outside the mandate; "
            f"enforced delta {_show(enforced)}"
        )


class InvariantGate(_FortressGate):
    """OMEGA. The kernel's hard bounds on a run's state.

    Candidate: ``{"state": s, "distortion": d, "error": e, "volatility": v}``,
    the arguments of ``InvariantMonitor.check``. Any violation is a terminal
    breach, and so is any non-finite input, which the kernel's comparisons
    would read as no violation. The gate mirrors the monitor, asymmetry
    included: ``error``, ``distortion`` and ``volatility`` are bounded from
    above only, so a large negative error passes, as it does in the kernel.
    """

    name = "invariants"
    _KEYS = ("state", "distortion", "error", "volatility")

    def _normalize(self, candidate: object) -> Dict[str, Any]:
        found = _mapping(self.name, candidate, self._KEYS)
        return {key: _real(key, found[key]) for key in self._KEYS}

    def _content(self, values: Dict[str, Any]) -> Dict[str, Any]:
        return {key: _scalar(values[key]) for key in self._KEYS}

    def _decide(self, values: Dict[str, Any]) -> Tuple[bool, bool, str]:
        violations = InvariantMonitor.check(
            state=values["state"],
            distortion=values["distortion"],
            error=values["error"],
            volatility=values["volatility"],
        )
        bad = [key for key in self._KEYS if not _finite(values[key])]
        parts = []
        if violations:
            parts.append("invariant violation: " + ", ".join(violations))
        if bad:
            parts.append(f"non-finite input ({', '.join(bad)}): invariants cannot be decided")
        if not parts:
            return True, False, ""
        return False, False, "; ".join(parts)


class AuditChainGate(_FortressGate):
    """OMEGA. The kernel's verdict on its own audit chain.

    Candidate: an ``ImmutableAuditLedger`` (for a kernel, ``fortress.audit``).
    Verification that returns anything but ``True``, or raises, is a terminal
    breach. So is a ledger CNS cannot describe, whatever shape the tampering
    took: that verdict is unbound. The gate does not raise for tampered content.
    """

    name = "audit_chain"

    def _normalize(self, candidate: object) -> Dict[str, Any]:
        if not isinstance(candidate, ImmutableAuditLedger):
            raise TypeError(
                f"{self.name} judges an ImmutableAuditLedger; got {type(candidate).__name__}"
            )
        return {"ledger": candidate}

    def _content(self, values: Dict[str, Any]) -> Dict[str, Any]:
        try:
            records = _plain(values["ledger"].ledger)
        except Exception:  # a cycle (RecursionError), a ledger that lost its list, ...
            records = _Undescribable()
        return {"records": records}

    def _decide(self, values: Dict[str, Any]) -> Tuple[bool, bool, str]:
        try:
            intact = values["ledger"].verify_integrity()
        except Exception as exc:  # a tampered ledger can crash its own verifier
            return False, False, f"audit ledger verification raised {type(exc).__name__}: {exc}"
        if intact is True:
            return True, False, ""
        return False, False, "audit ledger failed verify_integrity()"


def cns_chain() -> Any:
    """A ``cns.gate.GateChain`` holding the kernel's gates at their declared ends.

    ``alpha`` (before the work): numeric safety, then mandate. ``omega`` (on
    the result): invariants, then the audit chain. Each gate takes its own
    candidate shape, so a consumer runs ``chain.alpha`` on the request and
    ``chain.omega`` on what the run produced.
    """
    cns = _cns_gate()
    return cns.GateChain(
        alpha=(NumericSafetyGate(), MandateGate()),
        omega=(InvariantGate(), AuditChainGate()),
    )
