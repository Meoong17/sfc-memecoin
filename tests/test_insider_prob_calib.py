"""Test Insider P2: calibrated logistic insider probability (Phase 4)."""
import pytest

from engines.insider_prob_calib import InsiderSample, LogisticInsiderModel


def _sample(early, cluster, ita, dist, lead, label):
    return InsiderSample([early, cluster, ita, dist, lead], label)


def _synthetic_train(n=120):
    """Generate separable-ish synthetic labeled data.

    Insider (label=1): early entry + funding cluster + high ITA.
    Non-insider (label=0): late entry, no cluster, low ITA.
    """
    import random
    rng = random.Random(42)
    samples = []
    for _ in range(n):
        insider = rng.random() < 0.5
        if insider:
            early, cluster = 1.0, 1.0
            ita = rng.uniform(0.6, 1.0)
            dist = 1.0 if rng.random() < 0.7 else 0.0
            lead = rng.uniform(0.4, 1.0)
        else:
            early, cluster = 0.0, 0.0
            ita = rng.uniform(0.0, 0.3)
            dist = 0.0
            lead = rng.uniform(0.0, 0.1)
        samples.append(_sample(early, cluster, ita, dist, lead, 1 if insider else 0))
    return samples


def test_not_fitted_raises():
    m = LogisticInsiderModel()
    with pytest.raises(RuntimeError):
        m.predict_proba([1.0, 1.0, 0.8, 1.0, 0.5])


def test_predict_before_fit_invalid():
    m = LogisticInsiderModel()
    with pytest.raises(RuntimeError):
        m.calibration_stats([])


def test_fit_and_high_probability_for_insider_features():
    train = _synthetic_train(200)
    m = LogisticInsiderModel().fit(train, epochs=3000)
    assert m.fitted
    # insider-like features -> high probability
    p_ins = m.predict_proba([1.0, 1.0, 0.9, 1.0, 0.9])
    p_org = m.predict_proba([0.0, 0.0, 0.1, 0.0, 0.05])
    assert p_ins > 0.7
    assert p_org < 0.3


def test_calibration_accuracy_on_holdout():
    train = _synthetic_train(200)
    holdout = _synthetic_train(60)
    m = LogisticInsiderModel().fit(train, epochs=3000)
    stats = m.calibration_stats(holdout)
    assert stats["n"] == 60
    assert stats["accuracy"] >= 0.7
    assert 0.0 <= stats["brier_score"] <= 0.3


def test_wrong_feature_count_raises():
    train = _synthetic_train(100)
    m = LogisticInsiderModel().fit(train)
    with pytest.raises(ValueError):
        m.predict_proba([1.0, 1.0])  # only 2 features


def test_empty_train_raises():
    with pytest.raises(ValueError):
        LogisticInsiderModel().fit([])


def test_summary_shape():
    m = LogisticInsiderModel().fit(_synthetic_train(100))
    s = m.summary()
    assert s["fitted"] is True
    assert len(s["weights"]) == 5
