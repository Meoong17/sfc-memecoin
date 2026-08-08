"""Test the Measurement Contract (v5 §3): one producer, shared consumers, no double-counting."""
import pytest

from evidence.registry import (
    EvidenceRegistry,
    MeasurementContractError,
    build_canonical_registry,
)


def test_single_producer_per_evidence():
    reg = EvidenceRegistry()
    reg.register_producer("EV-X", "producer_a")
    with pytest.raises(MeasurementContractError):
        reg.register_producer("EV-X", "producer_b")
    assert reg.producer_of("EV-X") == "producer_a"


def test_consumer_requires_producer_first():
    reg = EvidenceRegistry()
    with pytest.raises(MeasurementContractError):
        reg.register_consumer("EV-Y", "some engine")
    reg.register_producer("EV-Y", "producer_a")
    reg.register_consumer("EV-Y", "engine_b")  # OK now


def test_unknown_evidence_raises():
    reg = EvidenceRegistry()
    with pytest.raises(MeasurementContractError):
        reg.evidence("EV-Z")


def test_canonical_ev021_shared_across_three_engines():
    """Spec §6.6.2: EV-021 consumed by Wallet Graph, Sybil, Insider — same evidence, no 3x recompute."""
    reg = build_canonical_registry()
    assert reg.producer_of("EV-021") == "data_sources.wallet_funding"
    consumers = reg.consumers_of("EV-021")
    assert {"Wallet Graph", "Sybil Score", "Insider Intel"} <= consumers


def test_engines_sharing_evidence_are_not_independent():
    """Confidence must discount engines sharing an Evidence ID."""
    reg = build_canonical_registry()
    # All three share EV-021 -> not independent
    assert reg.independence_factor(("Wallet Graph", "Sybil Score")) < 1.0
    assert reg.independence_factor(("Wallet Graph", "Insider Intel")) < 1.0
    assert reg.independence_factor(("Sybil Score", "Insider Intel")) < 1.0
    # Microstructure and Wallet Graph share no evidence -> fully independent
    assert reg.independence_factor(("Microstructure", "Wallet Graph")) == 1.0


def test_shared_evidence_listing():
    reg = build_canonical_registry()
    assert reg.shared_evidence(("Wallet Graph", "Sybil Score")) == {"EV-021"}
    assert reg.shared_evidence(("Microstructure", "Social Bot")) == set()


def test_assert_no_double_counting_passes():
    build_canonical_registry().assert_no_double_counting()


def test_evidence_meta_roundtrip():
    reg = build_canonical_registry()
    ev = reg.evidence("EV-021")
    assert ev.name == "Funding graph cluster"
    assert ev.normalization == "cluster"
    assert "Insider Intel" in ev.consumers
