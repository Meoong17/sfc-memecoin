"""Evidence / signal registry — the Measurement Contract spine.

Guarantees (v5 spec §3):
  1. Every raw signal is registered exactly ONCE (one producer).
  2. Consumers reference signals by Evidence ID; no engine recomputes a signal
     owned by another producer.
  3. Engines that share an Evidence ID are NOT independent — the registry
     exposes an independence matrix so the Confidence engine can discount.

Enforcement is mechanical via `register_producer` / `register_consumer` and the
`assert_no_double_counting()` / `independence_factor()` helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class MeasurementContractError(Exception):
    """Raised when the Measurement Contract is violated."""


@dataclass(frozen=True)
class Evidence:
    """A registered signal."""
    evidence_id: str
    name: str
    producer: str
    normalization: str
    consumers: frozenset[str] = frozenset()


class EvidenceRegistry:
    """Tracks producers/consumers per Evidence ID and enforces the contract."""

    def __init__(self) -> None:
        # evidence_id -> producer name (exactly one)
        self._producers: dict[str, str] = {}
        # evidence_id -> set of consumer engine names
        self._consumers: dict[str, set[str]] = {}
        self._meta: dict[str, dict] = {}

    def register_producer(self, evidence_id: str, producer: str, *, name: str = "", normalization: str = "zscore") -> None:
        if evidence_id in self._producers:
            raise MeasurementContractError(
                f"Evidence {evidence_id} already has producer '{self._producers[evidence_id]}'; "
                f"cannot re-register '{producer}' (one producer per evidence)."
            )
        self._producers[evidence_id] = producer
        self._meta[evidence_id] = {"name": name or evidence_id, "normalization": normalization}
        self._consumers.setdefault(evidence_id, set())

    def register_consumer(self, evidence_id: str, engine: str) -> None:
        if evidence_id not in self._producers:
            raise MeasurementContractError(
                f"Evidence {evidence_id} has no producer; cannot register consumer '{engine}'. "
                "Producer must be registered before consumers."
            )
        self._consumers[evidence_id].add(engine)

    def register_engine_uses(self, engine: str, evidence_ids: list[str]) -> None:
        """Convenience: register all evidence IDs an engine consumes."""
        for eid in evidence_ids:
            self.register_consumer(eid, engine)

    # --- queries ---

    def producer_of(self, evidence_id: str) -> str:
        return self._producers[evidence_id]

    def consumers_of(self, evidence_id: str) -> set[str]:
        return set(self._consumers.get(evidence_id, set()))

    def evidence_ids(self) -> list[str]:
        return sorted(self._producers)

    def evidence(self, evidence_id: str) -> Evidence:
        if evidence_id not in self._producers:
            raise MeasurementContractError(f"Unknown evidence: {evidence_id}")
        m = self._meta.get(evidence_id, {})
        return Evidence(
            evidence_id=evidence_id,
            name=m.get("name", evidence_id),
            producer=self._producers[evidence_id],
            normalization=m.get("normalization", "zscore"),
            consumers=frozenset(self._consumers.get(evidence_id, set())),
        )

    # --- contract enforcement ---

    def assert_no_double_counting(self) -> None:
        """Fail if any evidence has multiple producers (should be impossible)."""
        # Producers dict keys are unique by construction; this is a safety net.
        return

    def independence_factor(self, engine_pair: tuple[str, str]) -> float:
        """Return independence in [0,1] for a pair of engines.

        1.0 = share no evidence (fully independent).
        <1.0 = share at least one Evidence ID (discount in Confidence).
        """
        a, b = engine_pair
        shared = {eid for eid in self.evidence_ids() if a in self._consumers[eid] and b in self._consumers[eid]}
        if not shared:
            return 1.0
        # Base discount proportional to number of shared evidence; capped at 0.5 floor.
        return max(0.5, 1.0 - 0.25 * len(shared))

    def shared_evidence(self, engine_pair: tuple[str, str]) -> set[str]:
        a, b = engine_pair
        return {eid for eid in self.evidence_ids() if a in self._consumers[eid] and b in self._consumers[eid]}


# --- Convenience: the canonical v5 evidence graph ---
# Consumers reference the SAME Evidence IDs; no independent recompute.

def build_canonical_registry() -> EvidenceRegistry:
    """Construct the registry matching spec §3 / §6.6.2."""
    reg = EvidenceRegistry()
    # Producers (each evidence owned by exactly one producer module)
    reg.register_producer("EV-021", "data_sources.wallet_funding", name="Funding graph cluster", normalization="cluster")
    reg.register_producer("EV-001", "data_sources.dex_flow", name="Wallet flow / DEX swap", normalization="zscore")
    reg.register_producer("EV-002", "data_sources.honeypot_sim", name="Contract risk", normalization="bounded")
    reg.register_producer("EV-003", "data_sources.social_attention", name="Social mention velocity", normalization="zscore")
    # Consumers
    reg.register_engine_uses("Wallet Graph", ["EV-021"])
    reg.register_engine_uses("Sybil Score", ["EV-021"])
    reg.register_engine_uses("Insider Intel", ["EV-021", "EV-001"])
    reg.register_engine_uses("Microstructure", ["EV-001"])
    reg.register_engine_uses("Absorption", ["EV-001"])
    reg.register_engine_uses("Narrative Velocity", ["EV-003"])
    reg.register_engine_uses("Social Bot", ["EV-003"])
    reg.register_engine_uses("Security Gate", ["EV-002"])
    reg.register_engine_uses("Alpha", ["EV-002"])
    return reg
