"""Test Insider P3 ML classifier (Phase 5)."""
import pytest

from engines.insider_classifier import InsiderMLClassifier, LaunchFeatures


def _lf(token, early, cluster, ita, dist, lead, label):
    return LaunchFeatures(token=token, wallet="W", early_entry=early,
                          funding_cluster=cluster, ita=ita, distribution=dist,
                          lead_norm=lead, outcome_insider=label)


def _synthetic_labeled(n=120):
    import random
    rng = random.Random(3)
    out = []
    for _ in range(n):
        insider = rng.random() < 0.5
        if insider:
            out.append(_lf(f"t{_}", 1.0, 1.0, rng.uniform(0.6, 1.0), 1.0, rng.uniform(0.4, 1.0), True))
        else:
            out.append(_lf(f"t{_}", 0.0, 0.0, rng.uniform(0.0, 0.3), 0.0, rng.uniform(0.0, 0.1), False))
    return out


def test_unfitted_returns_low_default():
    cl = InsiderMLClassifier()
    r = cl.classify("W", "TOK", _lf("TOK", 1.0, 1.0, 0.9, 1.0, 0.9, False))
    assert not r.is_insider
    assert "model_unfitted_default_low" in r.reasons


def test_fit_and_classify_insider():
    cl = InsiderMLClassifier().fit(_synthetic_labeled(160), epochs=2000)
    r_ins = cl.classify("W", "TOK", _lf("TOK", 1.0, 1.0, 0.9, 1.0, 0.9, False))
    r_org = cl.classify("W", "TOK", _lf("TOK", 0.0, 0.0, 0.1, 0.0, 0.05, False))
    assert r_ins.is_insider
    assert not r_org.is_insider
    assert r_ins.probability > r_org.probability


def test_similarity_boost_to_confirmed_insider_pool():
    cl = InsiderMLClassifier().fit(_synthetic_labeled(160), epochs=2000)
    # register a confirmed insider reference
    cl.register_labeled([_lf("ref", 1.0, 1.0, 0.9, 1.0, 0.9, True)])
    r = cl.classify("W", "TOK", _lf("TOK", 1.0, 1.0, 0.85, 1.0, 0.85, False))
    assert r.similarity_boost > 0.5  # close to confirmed insider reference
    assert r.is_insider


def test_cosine_similarity_high_for_matching():
    from engines.insider_classifier import _cosine
    assert _cosine([1, 1, 1], [1, 1, 1]) == pytest.approx(1.0)
    assert _cosine([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_summary_shape():
    cl = InsiderMLClassifier().fit(_synthetic_labeled(100), epochs=1000)
    r = cl.classify("W", "TOK", _lf("TOK", 1.0, 1.0, 0.8, 1.0, 0.8, False))
    s = r.summary()
    for k in ["wallet", "token", "probability", "is_insider",
              "similarity_boost", "reasons"]:
        assert k in s
