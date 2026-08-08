#!/usr/bin/env python3
"""Phase 4 smoke test: absorption + regime + calibrated insider probability.

Uses a synthetic labeled dataset to fit the logistic insider model, then
verifies it separates insider-like from organic-like feature vectors, plus
absorption and regime sanity.

Run: .venv/bin/python scripts/smoke_phase4.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.absorption import AbsorptionEngine, AbsorptionInputs
from engines.insider_prob_calib import InsiderSample, LogisticInsiderModel
from engines.regime import SeriesInput, RegimeEngine


def _synthetic_train(n=200):
    import random
    rng = random.Random(7)
    samples = []
    for _ in range(n):
        insider = rng.random() < 0.5
        if insider:
            feats = [1.0, 1.0, rng.uniform(0.6, 1.0), 1.0 if rng.random() < 0.7 else 0.0, rng.uniform(0.4, 1.0)]
        else:
            feats = [0.0, 0.0, rng.uniform(0.0, 0.3), 0.0, rng.uniform(0.0, 0.1)]
        samples.append(InsiderSample(feats, 1 if insider else 0))
    return samples


def main() -> int:
    print("=== SFC Memecoin Phase 4 smoke test ===")

    # --- calibrated insider probability ---
    train = _synthetic_train(240)
    model = LogisticInsiderModel().fit(train, epochs=3000)
    stats = model.calibration_stats(train)
    p_ins = model.predict_proba([1.0, 1.0, 0.9, 1.0, 0.9])
    p_org = model.predict_proba([0.0, 0.0, 0.1, 0.0, 0.05])
    print(f"\nCalibrated insider model: fitted={model.fitted}")
    print(f"  weights = {model.summary()['weights']}  bias = {model.summary()['bias']}")
    print(f"  train accuracy = {stats['accuracy']}  brier = {stats['brier_score']}")
    print(f"  P(insider | insider-features) = {p_ins:.3f}")
    print(f"  P(insider | organic-features) = {p_org:.3f}")
    assert p_ins > 0.7, "insider-like features must give high probability"
    assert p_org < 0.3, "organic-like features must give low probability"

    # --- absorption ---
    abs_eng = AbsorptionEngine()
    absorb = abs_eng.compute("TOK_A", AbsorptionInputs(
        demand=0.9, liquidity=0.8, smart_money=0.8, holder_growth=0.7,
        buy_pressure=0.9, social_attention=0.8, price_response=0.2,
        whale_selling=0.1, liquidity_stress=0.1, insider_supply=0.0))
    no_absorb = abs_eng.compute("TOK_B", AbsorptionInputs(
        demand=0.3, liquidity=0.3, smart_money=0.2, holder_growth=0.2,
        buy_pressure=0.3, social_attention=0.9, price_response=0.9,
        whale_selling=0.8, liquidity_stress=0.5, insider_supply=0.5))
    print(f"\nAbsorption: TOK_A detected={absorb.absorption_detected} (score {absorb.absorption_score:.2f})")
    print(f"            TOK_B detected={no_absorb.absorption_detected} (score {no_absorb.absorption_score:.2f})")
    assert absorb.absorption_detected and not no_absorb.absorption_detected

    # --- regime ---
    reg = RegimeEngine()
    r_break = reg.analyze("TOK_A", [SeriesInput("price", list(range(0, 60)), high_is_bullish=True)])
    r_coll = reg.analyze("TOK_B", [SeriesInput("liq_stress",
                                               [0.1] * 30 + [round(0.1 + 0.04 * i, 2) for i in range(20)],
                                               high_is_bullish=False)])
    print(f"\nRegime: TOK_A={r_break.regime} (z={r_break.composite_z:.2f})")
    print(f"        TOK_B={r_coll.regime} (z={r_coll.composite_z:.2f})")
    assert r_break.composite_z > 0 and r_coll.composite_z < 0

    print("\n=== PASS: Phase 4 absorption/regime/calibrated-insider all correct ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
