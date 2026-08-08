"""Test SQLite Actor Reputation persistence (Phase 3)."""
from reputation.sqlite_db import SQLiteActorReputationDB


def test_persist_roundtrip_in_memory():
    db = SQLiteActorReputationDB()  # :memory:
    db.register_dev("devA", "solana", launches=5, rugged=2, lps_removed=1)
    prof = db.lookup("devA", "solana")
    assert prof is not None and prof.role_tag == "dev"
    assert prof.launches == 5


def test_persist_to_file_and_reload(tmp_path):
    path = tmp_path / "rep.db"
    # write
    db = SQLiteActorReputationDB(path)
    db.register_dev("devB", "bsc", launches=10, rugged=7, lps_removed=5)
    db.close()
    # reload from same file
    db2 = SQLiteActorReputationDB(path)
    prof = db2.lookup("devB", "bsc")
    assert prof is not None
    assert prof.rugged == 7
    assert prof.dev_score < 30  # bad dev
    db2.close()


def test_upsert_overwrites_on_conflict(tmp_path):
    path = tmp_path / "rep2.db"
    db = SQLiteActorReputationDB(path)
    db.register_dev("devC", "solana", launches=3, rugged=1)
    db.close()
    db2 = SQLiteActorReputationDB(path)
    db2.register_dev("devC", "solana", launches=8, rugged=6, lps_removed=4)
    prof = db2.lookup("devC", "solana")
    assert prof.launches == 8  # updated, not duplicated
    assert db2.count() == 1
    db2.close()


def test_lookup_missing_returns_none():
    db = SQLiteActorReputationDB()
    assert db.lookup("ghost", "solana") is None


def test_insider_profile_persisted(tmp_path):
    path = tmp_path / "rep3.db"
    db = SQLiteActorReputationDB(path)
    db.register_insider("ins1", "solana", median_entry_lead=25.0, common_funders=2)
    db.close()
    db2 = SQLiteActorReputationDB(path)
    prof = db2.lookup("ins1", "solana")
    assert prof is not None and prof.role_tag == "insider"
    assert prof.median_entry_lead == 25.0
    db2.close()
