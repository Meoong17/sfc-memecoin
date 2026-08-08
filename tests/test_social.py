"""Test EV-003 producer + Social Bot Organicity (Phase 3)."""
from datetime import datetime, timedelta

import pytest

from data_sources.social_attention import Mention, SocialSnapshot, aggregate_mentions
from engines.social_bot import SocialBotDetector, SocialOrganicityInputs


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def _snap(token, n_authors, n_mentions, platform="twitter", engagement=0):
    mentions = [Mention(f"a{i % n_authors}", f"m{i}", _t(0), platform)
                for i in range(n_mentions)]
    return aggregate_mentions(token, mentions, _t(0), _t(1),
                              engagement_total=engagement)


det = SocialBotDetector()


def test_aggregate_mentions_counts():
    snap = _snap("TOK", n_authors=3, n_mentions=9)
    assert snap.total_mentions == 9
    assert snap.unique_authors == 3
    assert snap.author_diversity == pytest.approx(3 / 9)
    assert snap.mentions_by_platform["twitter"] == 9


def test_organic_high_diversity():
    # many distinct authors, low growth divergence, established accounts
    snap = _snap("TOK", n_authors=10, n_mentions=12, engagement=30)
    inp = SocialOrganicityInputs(snapshot=snap, prev_mentions=3, prev_unique_authors=2,
                                 avg_author_age_days=60.0)
    r = det.detect(inp)
    assert r.label == "ORGANIC"
    assert r.organicity_score >= 0.65


def test_artificial_low_diversity():
    # few authors spamming many mentions, fresh accounts
    snap = _snap("TOK", n_authors=2, n_mentions=50, engagement=5)
    inp = SocialOrganicityInputs(snapshot=snap, prev_mentions=1, prev_unique_authors=1,
                                 avg_author_age_days=1.0)
    r = det.detect(inp)
    assert r.label == "ARTIFICIAL"
    assert r.organicity_score <= 0.35


def test_empty_mentions_safe():
    snap = aggregate_mentions("TOK", [], _t(0), _t(1))
    inp = SocialOrganicityInputs(snapshot=snap)
    r = det.detect(inp)
    assert r.organicity_score == 0.0


def test_summary_shape():
    snap = _snap("TOK", n_authors=5, n_mentions=10)
    r = det.detect(SocialOrganicityInputs(snapshot=snap, avg_author_age_days=30.0))
    s = r.summary()
    for k in ["token", "organicity_score", "label", "reasons"]:
        assert k in s
