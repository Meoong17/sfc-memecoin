"""Confidence score engine (spec §7).

Confidence(model) = Evidence Quality x Evidence Independence x Data Completeness x Temporal Stability
Confidence(final) = Confidence(model) x DQI

Evidence Independence is computed from the Measurement Contract registry: engines
that share an Evidence ID are NOT independent and get discounted. Because
EV-021 is shared by Wallet Graph + Sybil + Insider, those engines lower the
overall independence term for any token scored with all three.

All component scores are clamped to [0,1].
"""
from __future__ import annotations

from dataclasses import dataclass, field

from evidence.registry import EvidenceRegistry

# DQI floor below which a token is dropped (config/thresholds.py)
DEFAULT_DQI_FLOOR = 0.5


@dataclass
class EngineScores:
    """Per-engine confidence component inputs (all [0,1] except stability raw)."""
    engine: str
    evidence_quality: float = 1.0
    completeness: float = 1.0
    stability: float = 1.0


@dataclass
class ConfidenceResult:
    model_confidence: float
    final_confidence: float
    dqi: float
    independence: float
    dqi_passed: bool
    components: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "model_confidence": round(self.model_confidence, 4),
            "final_confidence": round(self.final_confidence, 4),
            "dqi": round(self.dqi, 4),
            "independence": round(self.independence, 4),
            "dqi_passed": self.dqi_passed,
            "components": self.components,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def independence_for_engines(registry: EvidenceRegistry, engines: list[str]) -> float:
    """Aggregate independence across an engine set.

    Fully independent (no shared evidence) -> 1.0. For each shared-evidence
    pair we take the pairwise independence discount from the registry and
    combine as the minimum (the weakest link caps the whole set's independence).
    """
    if len(engines) < 2:
        return 1.0
    factors: list[float] = []
    n = len(engines)
    for i in range(n):
        for j in range(i + 1, n):
            factors.append(registry.independence_factor((engines[i], engines[j])))
    return _clamp01(min(factors) if factors else 1.0)


def compute_confidence(
    registry: EvidenceRegistry,
    engine_scores: list[EngineScores],
    *,
    dqi: float = 1.0,
    dqi_floor: float = DEFAULT_DQI_FLOOR,
) -> ConfidenceResult:
    """Compute model + final confidence for a set of scored engines."""
    if not engine_scores:
        # No engines scored -> cannot claim confidence.
        return ConfidenceResult(
            model_confidence=0.0, final_confidence=0.0, dqi=dqi,
            independence=1.0, dqi_passed=dqi >= dqi_floor,
            components={},
        )

    engines = [e.engine for e in engine_scores]
    indep = independence_for_engines(registry, engines)

    # Aggregate per-component quality across engines (mean is robust here).
    eq = _clamp01(sum(e.evidence_quality for e in engine_scores) / len(engine_scores))
    comp = _clamp01(sum(e.completeness for e in engine_scores) / len(engine_scores))
    stab = _clamp01(sum(e.stability for e in engine_scores) / len(engine_scores))

    model = _clamp01(eq * indep * comp * stab)

    dqi_c = _clamp01(dqi)
    final = model * dqi_c
    dqi_passed = dqi_c >= dqi_floor

    return ConfidenceResult(
        model_confidence=model,
        final_confidence=final,
        dqi=dqi_c,
        independence=indep,
        dqi_passed=dqi_passed,
        components={
            "evidence_quality": round(eq, 4),
            "independence": round(indep, 4),
            "completeness": round(comp, 4),
            "stability": round(stab, 4),
            "dqi": round(dqi_c, 4),
        },
    )
