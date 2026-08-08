"""Test backfill: KlineAnalyzer + DatasetBackfiller (mocked)."""
import pytest

from backfill import BackfillConfig, DatasetBackfiller, KlineAnalyzer
from backtest.labeler import Outcome
from fetchers.gmgn import GmgnFetcher


def _kline(closes, highs=None):
    highs = highs or closes
    out = []
    for i, c in enumerate(closes):
        out.append({"time": 1000 * (i + 1), "open": str(c), "close": str(c),
                    "high": str(highs[i]), "low": str(c * 0.9), "volume": "100"})
    return out


def test_kline_peak_return():
    closes = [1.0, 1.5, 2.0, 3.0, 2.5]
    highs = [1.0, 1.5, 2.0, 3.0, 2.5]
    m = KlineAnalyzer.analyze(_kline(closes, highs))
    assert m["peak_return_pct"] == 200.0  # base 1.0 -> peak 3.0


def test_kline_max_drawdown():
    # peak at 3.0 then drop to 1.5 -> dd = -50%
    closes = [1.0, 2.0, 3.0, 1.5]
    highs = [1.0, 2.0, 3.0, 1.5]
    m = KlineAnalyzer.analyze(_kline(closes, highs))
    assert m["max_drawdown_pct"] == pytest.approx(-50.0)
    assert m["days_observed"] == 4


def test_kline_empty_or_bad():
    assert KlineAnalyzer.analyze([]) is None
    assert KlineAnalyzer.analyze([{"close": "0"}]) is None


def test_backfiller_build_classifies(monkeypatch):
    """Mocked gmgn: 3 tokens -> rugged (big dd), pumped, survived."""
    f = GmgnFetcher(api_key="fake")

    # trenches returns universe
    def fake_run(*args, **kw):
        if args[0] == "market" and args[1] == "trenches":
            typ = args[5]  # ["market","trenches","--chain",chain,"--type",typ,...]
            if typ == "new_creation":
                return {"new_creation": [
                    {"address": "A", "created_timestamp": 1785877528, "is_token_live": True},
                    {"address": "B", "created_timestamp": 1785877528, "is_token_live": True},
                    {"address": "C", "created_timestamp": 1785877528, "is_token_live": True},
                ]}
            return {"completed": []}
        if args[0] == "market" and args[1] == "kline":
            addr = args[5]  # ["market","kline","--chain",chain,"--address",addr,...]
            if addr == "A":  # rugged: peak then crash
                return {"list": _kline([1.0, 2.0, 3.0, 0.5], [1.0, 2.0, 3.0, 0.5])}
            if addr == "B":  # pumped: sustained rise over 8 days
                return {"list": _kline([1.0, 2.0, 4.0, 8.0, 12.0, 15.0, 18.0, 20.0],
                                       [1.0, 2.0, 4.0, 8.0, 12.0, 15.0, 18.0, 20.0])}
            return {"list": _kline([1.0, 1.1, 1.2], [1.0, 1.1, 1.2])}  # survived
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(f, "_run", fake_run)
    import time
    cfg = BackfillConfig(chain="solana", max_tokens=3, min_launch_days_ago=0,
                         max_launch_days_ago=365, universe_mode="trenches")
    b = DatasetBackfiller(f, cfg)
    ds = b.build(progress=False)
    assert len(ds.samples) == 3
    by = {s.token: s.outcome for s in ds.samples}
    assert by["A"] == Outcome.RUGGED
    assert by["B"] == Outcome.PUMPED
    assert by["C"] == Outcome.SURVIVED


def test_backfiller_trending_universe_and_from_launch_kline(monkeypatch):
    """Default universe_mode='trending': uses market trending + kline from launch."""
    f = GmgnFetcher(api_key="fake")

    def fake_run(*args, **kw):
        if args[0] == "market" and args[1] == "trending":
            return {"data": {"rank": [
                {"address": "T1", "creation_timestamp": 1785877528,
                 "is_token_live": True, "bundler_rate": 0.5, "sniper_count": 10,
                 "rug_ratio": 0.2},
                {"address": "T2", "creation_timestamp": 1785877528,
                 "is_token_live": True, "bundler_rate": 0.1, "sniper_count": 0,
                 "rug_ratio": 0.02},
            ]}}
        if args[0] == "market" and args[1] == "kline":
            addr = args[5]  # --address at args[5]
            # verify --from/--to passed (launch-based backfill)
            assert "--from" in args
            if addr == "T1":  # rugged
                return {"data": {"list": _kline([1.0, 2.0, 3.0, 0.5], [1.0, 2.0, 3.0, 0.5])}}
            return {"data": {"list": _kline([1.0, 1.1, 1.2], [1.0, 1.1, 1.2])}}  # survived
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(f, "_run", fake_run)
    cfg = BackfillConfig(chain="solana", max_tokens=2, min_launch_days_ago=0,
                         max_launch_days_ago=365, universe_mode="trending",
                         trending_min_created="7d")
    b = DatasetBackfiller(f, cfg)
    ds = b.build(progress=False)
    assert len(ds.samples) == 2
    by = {s.token: s.outcome for s in ds.samples}
    assert by["T1"] == Outcome.RUGGED
    assert by["T2"] == Outcome.SURVIVED
    # insider features captured in note
    t1 = [s for s in ds.samples if s.token == "T1"][0]
    assert "bundler_rate=0.5" in t1.note
