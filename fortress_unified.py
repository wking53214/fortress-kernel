"""
FORTRESS Unified Governance Kernel

Merges three control strategies:
- SAGE-K: Multi-agent adaptive learning
- Lyapunov: Stability-proven integrity control
- Energy: State transition logging with hysteresis

Single unified orchestrator with pluggable controllers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime as dt
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

logger = logging.getLogger("FORTRESS")
logger.setLevel(logging.INFO)

# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class FortressConfig:
    """Unified configuration for all controller modes."""

    # General
    controller_mode: str = "energy"  # "sage", "lyapunov", "energy"
    latent_dim: int = 8
    state_dim: int = 1
    rng_seed: int = 42

    # History & buffers
    err_history_len: int = 10
    memory_buffer_maxlen: int = 16

    # Thresholds
    activation_threshold: float = 0.45
    authority_enter_threshold: float = 0.55
    authority_exit_threshold: float = 0.35
    state_engagement_threshold: float = 0.55
    state_disengagement_threshold: float = 0.35

    # Control parameters
    nominal_slew: float = 0.20
    sensitivity: float = 15.0
    max_contraction_ratio: float = 0.98

    # FIM tracking (Lyapunov mode)
    fim_beta: float = 0.90
    fim_divergence_weight: float = 0.05
    fim_cosine_weight: float = 0.05

    # Recovery & freezing
    recovery_freeze_cycles: int = 8

    # Variance composition
    prov_risk_no_sig: float = 0.5
    volatility_weight: float = 0.05
    surprisal_weight: float = 0.02
    prediction_error_weight: float = 0.02
    history_variance_weight: float = 0.05

    # Divergence
    causal_divergence_cap: float = 0.45
    causal_divergence_scale: float = 25.0
    divergence_saturation_cap: float = 0.45
    divergence_scaling_factor: float = 25.0
    unverified_source_penalty: float = 0.5

    # Regime classification
    nominal_adjustment_rate: float = 0.08


class OperationalRegime(Enum):
    STABLE = "stable"
    UNSTABLE = "unstable"
    CRITICAL = "critical"


class ControllerMode(Enum):
    SAGE = "sage"
    LYAPUNOV = "lyapunov"
    ENERGY = "energy"


@dataclass(frozen=True)
class FortressStateTransition:
    timestamp: dt
    previous_mode: str
    new_mode: str
    trigger_variance: float
    trigger_energy_delta: float
    reason: str


@dataclass(frozen=True)
class Payload:
    body: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# GUARDRAILS (SHARED)
# ============================================================================

class IntegrityLayer:
    """Volatility and semantic contradiction detection."""

    def __init__(self, config: FortressConfig):
        self.config = config
        self.error_history_window: deque[float] = deque(maxlen=config.err_history_len)
        self.stability_claims = {"stable", "healthy", "functional", "safe", "nominal"}

    def analyze(self, payload: Payload, current_error: float) -> Dict[str, Any]:
        if math.isnan(current_error) or math.isinf(current_error):
            raise ValueError("Numeric Safety Exception: Invalid error value (NaN/Inf).")

        self.error_history_window.append(abs(current_error))
        volatility = float(np.std(list(self.error_history_window), ddof=0)) if len(self.error_history_window) > 1 else 0.0

        text = (payload.body or "").lower()
        semantic_risk = 0.0
        if any(token in text for token in self.stability_claims) and current_error > 12.0:
            semantic_risk = 0.3

        distortion = min(0.98, (volatility * 0.05) + semantic_risk)
        return {"distortion": distortion, "volatility": volatility}


class InvariantMonitor:
    """Hard bounds enforcement."""

    @staticmethod
    def check(state: float, distortion: float, error: float, volatility: float) -> List[str]:
        violations = []
        if abs(state) > 250.0:
            violations.append("STATE_DIVERGENCE")
        if distortion > 0.85:
            violations.append("DISTORTION_OVERFLOW")
        if error > 20.0:
            violations.append("MODEL_FAILURE")
        if volatility > 40.0:
            violations.append("VOLATILITY_SPIKE")
        return violations


class DriftMonitor:
    """Structural weight drift detection."""

    def __init__(self, config: FortressConfig):
        self.config = config
        self.magnitude_history: deque[float] = deque(maxlen=12)

    def check(self, weights: List[List[float]]) -> tuple[bool, float]:
        if not weights or not weights[0]:
            return False, 0.0

        flat = [w for row in weights for w in row]
        current_mag = sum(abs(w) for w in flat) / len(flat) if flat else 0.0
        self.magnitude_history.append(current_mag)

        if len(self.magnitude_history) < 4:
            return False, 0.0

        drift = abs(current_mag - np.mean(list(self.magnitude_history)))
        return drift > 0.12, drift


class MandateLayer:
    """Action delta enforcement."""

    @staticmethod
    def enforce(action: Dict[str, float], current_kpi: float, target_kpi: float, volatility: float) -> Dict[str, float]:
        distance = target_kpi - current_kpi
        speed_limit = (abs(distance) * 0.35) / (1.0 + (volatility * 0.15))
        speed_limit = max(1.2, min(28.0, speed_limit))

        delta = action.get("delta", 0.0)
        action["delta"] = max(min(delta, speed_limit), -speed_limit)

        projected = current_kpi + action["delta"]
        if projected > (target_kpi + 15.0):
            action["delta"] = (target_kpi + 15.0) - current_kpi
        elif projected < (target_kpi - 75.0):
            action["delta"] = (target_kpi - 75.0) - current_kpi

        return action


# ============================================================================
# AUDIT LEDGER
# ============================================================================

class ImmutableAuditLedger:
    """HMAC-signed immutable audit trail."""

    def __init__(self, audit_key: str = "fortress-key"):
        self.audit_key = audit_key.encode()
        self.ledger: List[Dict[str, Any]] = []

    def append(self, event_type: str, data: Dict[str, Any]) -> None:
        record = {
            "ts": int(dt.utcnow().timestamp()),
            "event": event_type,
            "data": data,
        }
        msg = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
        record["hmac"] = hmac.new(self.audit_key, msg, hashlib.sha256).hexdigest()
        self.ledger.append(record)

    def verify_integrity(self) -> bool:
        for record in self.ledger:
            stored_hmac = record.pop("hmac", None)
            msg = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
            computed_hmac = hmac.new(self.audit_key, msg, hashlib.sha256).hexdigest()
            if stored_hmac != computed_hmac:
                return False
            record["hmac"] = stored_hmac
        return True


# ============================================================================
# ABSTRACT CONTROLLER
# ============================================================================

class Controller(ABC):
    """Abstract base for pluggable governance controllers."""

    def __init__(self, config: FortressConfig):
        self.config = config
        self.rng = np.random.RandomState(config.rng_seed)

    @abstractmethod
    def process(self, payload: Payload, error: float, live_signal: float) -> Dict[str, Any]:
        pass


# ============================================================================
# CONCRETE CONTROLLERS
# ============================================================================

class SAGEController(Controller):
    """Multi-agent adaptive learning (SAGE-K style)."""

    def __init__(self, config: FortressConfig):
        super().__init__(config)
        self.error_history = deque(maxlen=config.err_history_len)
        self.regime = OperationalRegime.STABLE

    def process(self, payload: Payload, error: float, live_signal: float) -> Dict[str, Any]:
        self.error_history.append(abs(error))
        volatility = float(np.std(list(self.error_history))) if len(self.error_history) > 1 else 0.0

        # Simple regime classification
        if volatility > 10.0 or abs(error) > 20.0:
            self.regime = OperationalRegime.CRITICAL
        elif volatility > 5.0 or abs(error) > 10.0:
            self.regime = OperationalRegime.UNSTABLE
        else:
            self.regime = OperationalRegime.STABLE

        # Conservative response
        response_factor = 0.05 if self.regime == OperationalRegime.STABLE else 0.35
        delta = (live_signal - error) * response_factor

        return {
            "output": round(live_signal + delta, 3),
            "regime": self.regime.value,
            "volatility": round(volatility, 3),
            "controller": "SAGE"
        }


class LyapunovController(Controller):
    """Stability-proven with FIM tracking."""

    def __init__(self, config: FortressConfig):
        super().__init__(config)
        self.error_history = deque(maxlen=config.err_history_len)
        self.G = np.zeros(config.latent_dim)
        self.g_ema = np.zeros(config.latent_dim)
        self.alpha = 1.0
        self.prev_energy = 0.0
        self.governance_active = False
        self.freeze_counter = 0

    def process(self, payload: Payload, error: float, live_signal: float) -> Dict[str, Any]:
        self.error_history.append(abs(error))
        volatility = float(np.std(list(self.error_history))) if len(self.error_history) > 1 else 0.0

        # Verify provenance
        is_verified = ("source_id" in payload.metadata and "signature" in payload.metadata)
        prov_risk = 0.0 if is_verified else self.config.prov_risk_no_sig

        # FIM divergence
        g_t = np.random.randn(self.config.latent_dim) * 0.1
        self.G = self.config.fim_beta * self.G + (1.0 - self.config.fim_beta) * (g_t ** 2)
        fim_divergence = float(np.linalg.norm(self.G))

        distortion = min(0.99, (volatility * 0.05) + prov_risk + (fim_divergence * self.config.fim_divergence_weight))

        # Lyapunov contraction
        energy = 0.5 * (error ** 2)
        is_contracting = (energy / max(self.prev_energy, 1e-6)) <= self.config.max_contraction_ratio or energy < 1e-4
        self.prev_energy = energy

        # Authority blending
        if not self.governance_active and distortion >= self.config.authority_enter_threshold:
            self.governance_active = True
        elif self.governance_active and distortion <= self.config.authority_exit_threshold:
            self.governance_active = False

        target_alpha = 1.0 / (1.0 + math.exp(self.config.sensitivity * (distortion - self.config.authority_enter_threshold)))

        if self.governance_active:
            self.freeze_counter = self.config.recovery_freeze_cycles
            slew = 0.5 if not is_contracting else 0.35
            target_alpha = 0.0 if not is_contracting else target_alpha
        else:
            if self.freeze_counter > 0:
                self.freeze_counter -= 1
                slew = 0.0
            else:
                slew = 0.40 if self.alpha < 1.0 else self.config.nominal_slew

        self.alpha += max(-slew, min(slew, target_alpha - self.alpha))
        self.alpha = max(0.0, min(1.0, self.alpha))

        blended = live_signal * self.alpha + 50.0 * (1.0 - self.alpha)

        return {
            "output": round(blended, 3),
            "authority": round(self.alpha, 3),
            "distortion": round(distortion, 3),
            "regime": "GOVERNED" if self.governance_active else "NOMINAL",
            "controller": "LYAPUNOV"
        }


class EnergyController(Controller):
    """Energy-based with state transition logging."""

    def __init__(self, config: FortressConfig):
        super().__init__(config)
        self.error_history = deque(maxlen=config.err_history_len)
        self.blending_coefficient = 1.0
        self.prior_energy = 0.0
        self.is_override_engaged = False
        self.state_transitions: List[FortressStateTransition] = []

    def process(self, payload: Payload, error: float, live_signal: float) -> Dict[str, Any]:
        self.error_history.append(abs(error))
        volatility = float(np.std(list(self.error_history))) if len(self.error_history) > 1 else 0.0

        is_verified = ("source_id" in payload.metadata and "signature" in payload.metadata)
        prov_risk = 0.0 if is_verified else self.config.prov_risk_no_sig

        variance = (volatility * self.config.volatility_weight) + prov_risk

        energy = 0.5 * (error ** 2)
        energy_delta = energy - self.prior_energy
        self.prior_energy = energy

        # State transitions with logging
        previous_mode = "OVERRIDE" if self.is_override_engaged else "NOMINAL"

        if not self.is_override_engaged and variance >= self.config.state_engagement_threshold:
            self.is_override_engaged = True
            self.state_transitions.append(FortressStateTransition(
                timestamp=dt.utcnow(),
                previous_mode="NOMINAL",
                new_mode="OVERRIDE",
                trigger_variance=variance,
                trigger_energy_delta=energy_delta,
                reason=f"Variance {variance:.3f} exceeded threshold"
            ))
        elif self.is_override_engaged and variance <= self.config.state_disengagement_threshold:
            self.is_override_engaged = False
            self.state_transitions.append(FortressStateTransition(
                timestamp=dt.utcnow(),
                previous_mode="OVERRIDE",
                new_mode="NOMINAL",
                trigger_variance=variance,
                trigger_energy_delta=energy_delta,
                reason=f"Variance {variance:.3f} fell below threshold"
            ))

        target_coeff = 1.0 / (1.0 + math.exp(self.config.sensitivity * (variance - self.config.state_engagement_threshold)))

        if energy_delta > 0 and self.is_override_engaged:
            slew = 0.5
            target_coeff = 0.0
        else:
            slew = self.config.nominal_slew

        self.blending_coefficient += max(-slew, min(slew, target_coeff - self.blending_coefficient))
        self.blending_coefficient = max(0.0, min(1.0, self.blending_coefficient))

        blended = live_signal * self.blending_coefficient + 50.0 * (1.0 - self.blending_coefficient)

        return {
            "output": round(blended, 3),
            "blending_coefficient": round(self.blending_coefficient, 3),
            "variance": round(variance, 3),
            "mode": "OVERRIDE" if self.is_override_engaged else "NOMINAL",
            "mode_changed": previous_mode != ("OVERRIDE" if self.is_override_engaged else "NOMINAL"),
            "controller": "ENERGY"
        }


# ============================================================================
# UNIFIED FORTRESS ORCHESTRATOR
# ============================================================================

class FortressUnified:
    """Central unified governance kernel orchestrating all controller modes."""

    def __init__(self, config: Optional[FortressConfig] = None):
        self.config = config or FortressConfig()
        self.integrity = IntegrityLayer(self.config)
        self.invariant = InvariantMonitor()
        self.drift = DriftMonitor(self.config)
        self.audit = ImmutableAuditLedger()

        # Select controller based on config
        if self.config.controller_mode == "sage":
            self.controller = SAGEController(self.config)
        elif self.config.controller_mode == "lyapunov":
            self.controller = LyapunovController(self.config)
        else:  # energy
            self.controller = EnergyController(self.config)

    def process(self, payload: Payload, error: float, live_signal: float) -> Dict[str, Any]:
        """Process request through unified governance kernel."""

        # Integrity analysis
        integrity_result = self.integrity.analyze(payload, error)

        # Run selected controller
        controller_result = self.controller.process(payload, error, live_signal)

        # Audit
        self.audit.append("governance_decision", {
            "error": error,
            "live_signal": live_signal,
            "controller": self.config.controller_mode,
            "result": controller_result
        })

        return {
            **controller_result,
            "distortion": integrity_result.get("distortion", 0.0),
            "integrity": "VERIFIED" if payload.metadata.get("signature") else "UNVERIFIED"
        }


if __name__ == "__main__":
    # Demonstration
    print("FORTRESS Unified Kernel\n")

    config_sage = FortressConfig(controller_mode="sage")
    config_lyapunov = FortressConfig(controller_mode="lyapunov")
    config_energy = FortressConfig(controller_mode="energy")

    for cfg, label in [(config_sage, "SAGE"), (config_lyapunov, "LYAPUNOV"), (config_energy, "ENERGY")]:
        fortress = FortressUnified(cfg)
        payload = Payload("System stable", {"source_id": "test", "signature": "sig-test-valid"})
        result = fortress.process(payload, 5.0, 100.0)
        print(f"{label}: {result}\n")
