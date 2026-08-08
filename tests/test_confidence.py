"""Test confidence engine (spec §7): multiplicative formula + evidence-overlap independence."""
import pytest

from evidence.registry import EvidenceRegistry, build_canonical_registry
from scoring.confidence import (
    EngineScores,
    compute_confidence,
    independence_for_engines,
)


def _scores(engines, eq=1.0, comp=1.0, stab=1.0):
    return [EngineScores(e, evidence_quality=eq, completeness=comp, stability=stab) for e in engines]


def test_all_perfect_scores():
    reg = EvidenceRegistry()
    # register a couple independent evidence so engines are independent
    reg.register_producer("EV-A", "pa", normalization="zscore")
    reg.register_producer("EV-B", "pb", normalization="zscore")
    reg.register_engine_uses("E1", ["EV-A"])
    reg.register_engine_uses("E2", ["EV-B"])
    res = compute_confidence(reg, _scores(["E1", "E2"]), dqi=1.0)
    assert res.dqi_passed
    assert res.final_confidence == pytest.approx(1.0, abs=1e-4)


def test_dqi_scales_final_only():
    reg = build_canonical_registry()
    res = compute_confidence(reg, _scores(["Security Gate", "Microstructure"]), dqi=0.8)
    assert res.model_confidence == pytest.approx(1.0, abs=1e-4)
    assert res.final_confidence == pytest.approx(0.8, abs=1e-4)


def test_dqi_floor_blocks_low_quality():
    reg = build_canonical_registry()
    res = compute_confidence(reg, _scores(["Security Gate"]), dqi=0.3, dqi_floor=0.5)
    assert not res.dqi_passed


def test_shared_evidence_reduces_independence():
    """EV-021 shared by Wallet Graph + Sybil + Insider -> not independent -> discount."""
    reg = build_canonical_registry()
    independent = independence_for_engines(reg, ["Microstructure", "Security Gate"])
    shared = independence_for_engines(reg, ["Wallet Graph", "Sybil Score", "Insider Intel"])
    assert shared < independent


def test_independence_single_engine_is_one():
    reg = build_canonical_registry()
    assert independence_for_engines(reg, ["Security Gate"]) == 1.0


def test_independence_empty_is_one():
    reg = build_canonical_registry()
    assert independence_for_engines(reg, []) == 1.0


def test_no_engines_zero_confidence():
    reg = build_canonical_registry()
    res = compute_confidence(reg, [], dqi=1.0)
    assert res.model_confidence == 0.0
    assert res.final_confidence == 0.0


def test_component_quality_lowers_confidence():
    reg = build_canonical_registry()
    res = compute_confidence(reg, _scores(["Security Gate", "Microstructure"], eq=0.6), dqi=1.0)
    assert res.components["evidence_quality"] == pytest.approx(0.6, abs=1e-4)
    assert res.final_confidence == pytest.approx(0.6, abs=1e-4)


def test_summary_shape():
    reg = build_canonical_registry()
    res = compute_confidence(reg, _scores(["Security Gate"]), dqi=0.9)
    s = res.summary()
    assert set(s.keys()) == {"model_confidence", "final_confidence", "dqi",
                             "independence", "dqi_passed", "components"}
    assert all(0.0 <= v <= 1.0 for k, v in s.items() if isinstance(v, float))
