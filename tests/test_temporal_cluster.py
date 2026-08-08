"""Test Temporal Wallet Clustering (Insider P1, Phase 3)."""
import pytest

from engines.temporal_cluster import TemporalWalletClusterer, WalletEntryRecord
from reputation.actor_reputation import ActorReputationDB


def _rec(wallet, chain, lead, early, funded=False):
    return WalletEntryRecord(wallet=wallet, chain=chain, token="T",
                             entry_lead_minutes=lead, early_entry=early,
                             in_funding_cluster=funded)


def test_consistent_early_entries_reputed_insider():
    db = ActorReputationDB()
    cl = TemporalWalletClusterer(db)
    records = [_rec("W1", "solana", 30.0, True, funded=True) for _ in range(4)]
    results = cl.cluster(records)
    assert len(results) == 1
    r = results[0]
    assert r.early_rate == 1.0
    assert r.is_reputed_insider
    assert r.reputation_confirmed
    # DB updated with insider profile
    prof = db.lookup("W1", "solana")
    assert prof is not None and prof.role_tag == "insider"
    assert prof.median_entry_lead == 30.0


def test_inconsistent_entries_not_reputed():
    db = ActorReputationDB()
    cl = TemporalWalletClusterer(db)
    records = [_rec("W2", "solana", 30.0, True),
               _rec("W2", "solana", -5.0, False),
               _rec("W2", "solana", -10.0, False)]
    results = cl.cluster(records)
    r = results[0]
    assert r.early_rate == pytest.approx(1 / 3)
    assert not r.is_reputed_insider
    assert not r.reputation_confirmed


def test_too_few_launches_not_judged():
    cl = TemporalWalletClusterer()
    results = cl.cluster([_rec("W3", "solana", 30.0, True)])  # only 1 launch
    assert results[0].is_reputed_insider is False  # not enough evidence


def test_median_lead_computation():
    cl = TemporalWalletClusterer()
    records = [_rec("W4", "solana", 10.0, True),
               _rec("W4", "solana", 40.0, True),
               _rec("W4", "solana", 20.0, True)]
    r = cl.cluster(records)[0]
    assert r.median_lead_minutes == 20.0
    assert r.is_reputed_insider


def test_groups_by_chain():
    db = ActorReputationDB()
    cl = TemporalWalletClusterer(db)
    records = [_rec("W5", "solana", 30.0, True), _rec("W5", "bsc", 30.0, True)]
    results = cl.cluster(records)
    # two separate chain-scoped groups
    assert len(results) == 2
    assert not any(r.reputation_confirmed for r in results)  # only 1 launch each
