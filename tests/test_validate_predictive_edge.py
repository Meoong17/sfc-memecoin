"""Test the predictive-edge validation harness helpers (not a claim of edge)."""
from scripts.validate_predictive_edge import auc_rank, pearson, historical_proxy


def test_auc_perfect_and_coin_flip():
    # perfect separation: score 1 for positives, 0 for negatives
    y = [1, 1, 0, 0]
    s = [1.0, 0.9, 0.1, 0.0]
    assert auc_rank(y, s) == 1.0
    # reversed -> 0
    assert auc_rank(y, [0.1, 0.0, 1.0, 0.9]) == 0.0
    # coin flip -> 0.5
    assert abs(auc_rank([1, 0, 1, 0], [1.0, 1.0, 0.0, 0.0]) - 0.5) < 1e-9


def test_auc_handles_single_class():
    # single class -> AUC undefined (nan); helper returns nan without crashing
    import math
    r = auc_rank([1, 1, 1], [0.1, 0.2, 0.3])
    assert math.isnan(r)


def test_pearson_perfect_and_zero():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert abs(pearson(xs, [2.0, 4.0, 6.0, 8.0]) - 1.0) < 1e-9
    assert abs(pearson(xs, [1.0, 1.0, 1.0, 1.0])) < 1e-9  # flat ys -> 0


def test_historical_proxy_maps_note():
    note = ("holder_count=100000; is_honeypot=0; bundler_rate=0.9; "
            "dev_team_hold_rate=0.2; rug_ratio=0.9; entrapment_ratio=0.5; "
            "renounced_mint=1")
    p = historical_proxy(note)
    # heavy bundler + dev hold + rug -> organic penalized below 50
    assert p["organic"] < 50.0
    # not honeypot + renounced -> safety high
    assert p["safety"] >= 75.0
    assert 0.0 <= p["raa"] <= 100.0


def test_historical_proxy_honeypot_low_safety():
    p = historical_proxy("is_honeypot=1; holder_count=1000; bundler_rate=0; "
                         "dev_team_hold_rate=0; rug_ratio=0; entrapment_ratio=0; "
                         "renounced_mint=0")
    assert p["safety"] <= 20.0
