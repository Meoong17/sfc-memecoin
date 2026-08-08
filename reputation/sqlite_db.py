"""Actor Reputation persistence — SQLite storage (Phase 3).

Keeps dev + insider profiles in one schema, persisted to SQLite (stdlib
sqlite3, no extra dependency). In-memory default for tests; pass a path for
production persistence. Preserves the same API as ActorReputationDB so engines
that take an ActorReputationDB still work (duck-typing).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from reputation.actor_reputation import ActorProfile, ActorReputationDB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actor_profiles (
    wallet      TEXT NOT NULL,
    chain       TEXT NOT NULL,
    role_tag    TEXT NOT NULL,
    launches    INTEGER DEFAULT 0,
    tokens_entered INTEGER DEFAULT 0,
    successful  INTEGER DEFAULT 0,
    rugged      INTEGER DEFAULT 0,
    abandoned   INTEGER DEFAULT 0,
    median_entry_lead REAL,
    profitability REAL,
    win_rate    REAL,
    avg_hold_time REAL,
    distribution_behavior TEXT DEFAULT 'UNKNOWN',
    common_funders INTEGER DEFAULT 0,
    cluster_id  TEXT,
    confidence  REAL DEFAULT 0.5,
    lps_removed INTEGER DEFAULT 0,
    PRIMARY KEY (wallet, chain)
)
"""


class SQLiteActorReputationDB(ActorReputationDB):
    """SQLite-backed Actor Reputation store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        super().__init__()  # keeps in-memory cache for fast lookups
        self.db_path = str(db_path) if db_path else ":memory:"
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._load_into_memory()

    def _load_into_memory(self) -> None:
        rows = self._conn.execute("SELECT * FROM actor_profiles").fetchall()
        for r in rows:
            self._profiles[f"{r['chain']}:{r['wallet']}"] = ActorProfile(
                wallet=r["wallet"], chain=r["chain"], role_tag=r["role_tag"],
                launches=r["launches"], tokens_entered=r["tokens_entered"],
                successful=r["successful"], rugged=r["rugged"],
                abandoned=r["abandoned"], median_entry_lead=r["median_entry_lead"],
                profitability=r["profitability"], win_rate=r["win_rate"],
                avg_hold_time=r["avg_hold_time"],
                distribution_behavior=r["distribution_behavior"],
                common_funders=r["common_funders"], cluster_id=r["cluster_id"],
                confidence=r["confidence"], lps_removed=r["lps_removed"],
            )

    def upsert(self, profile: ActorProfile) -> None:
        super().upsert(profile)
        self._conn.execute(
            """INSERT INTO actor_profiles
               (wallet, chain, role_tag, launches, tokens_entered, successful,
                rugged, abandoned, median_entry_lead, profitability, win_rate,
                avg_hold_time, distribution_behavior, common_funders,
                cluster_id, confidence, lps_removed)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(wallet, chain) DO UPDATE SET
                 role_tag=excluded.role_tag, launches=excluded.launches,
                 successful=excluded.successful, rugged=excluded.rugged,
                 abandoned=excluded.abandoned,
                 median_entry_lead=excluded.median_entry_lead,
                 win_rate=excluded.win_rate, confidence=excluded.confidence,
                 lps_removed=excluded.lps_removed
               """,
            (profile.wallet, profile.chain, profile.role_tag, profile.launches,
             profile.tokens_entered, profile.successful, profile.rugged,
             profile.abandoned, profile.median_entry_lead, profile.profitability,
             profile.win_rate, profile.avg_hold_time, profile.distribution_behavior,
             profile.common_funders, profile.cluster_id, profile.confidence,
             profile.lps_removed),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
