#!/usr/bin/env python3
"""Phase 3 smoke test: social + narrative + temporal cluster + reputation persistence.

Scenario: two tokens — one with organic social + a wallet that enters early
across many launches (reputed insider), one with bot-driven attention.

Run: .venv/bin/python scripts/smoke_phase3.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_sources.social_attention import Mention, aggregate_mentions
from engines.narrative_velocity import NarrativeDomain, NarrativeInputs, NarrativeVelocityEngine
from engines.social_bot import SocialBotDetector, SocialOrganicityInputs
from engines.temporal_cluster import TemporalWalletClusterer, WalletEntryRecord
from reputation.sqlite_db import SQLiteActorReputationDB


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def main() -> int:
    # --- Social bot detection ---
    det = SocialBotDetector()
    organic_mentions = [Mention(f"a{i}", f"m{i}", _t(0)) for i in range(80)]  # 80 distinct authors
    organic_snap = aggregate_mentions("ORGANIC_COIN", organic_mentions, _t(0), _t(1),
                                      engagement_total=240)
    organic = det.detect(SocialOrganicityInputs(
        snapshot=organic_snap, prev_mentions=30, prev_unique_authors=25,
        avg_author_age_days=90.0))

    bot_mentions = [Mention(f"bot{i % 3}", f"m{i}", _t(0)) for i in range(200)]  # 3 authors spam
    bot_snap = aggregate_mentions("BOT_COIN", bot_mentions, _t(0), _t(1),
                                  engagement_total=10)
    bot = det.detect(SocialOrganicityInputs(
        snapshot=bot_snap, prev_mentions=2, prev_unique_authors=1,
        avg_author_age_days=1.0))

    # --- Narrative velocity ---
    narr = NarrativeVelocityEngine()
    nv = narr.analyze(NarrativeInputs(
        token="ORGANIC_COIN",
        mention_series=[120, 190, 340, 720, 1450],
        domains=[
            NarrativeDomain("social", 1450, 120),
            NarrativeDomain("dex_flow", 300, 80),
            NarrativeDomain("wallets", 250, 90),
        ],
    ))

    # --- Temporal cluster + reputation persistence ---
    with tempfile.TemporaryDirectory() as td:
        rep_db = SQLiteActorReputationDB(Path(td) / "rep.db")
        cl = TemporalWalletClusterer(rep_db)
        # wallet enters early across 5 launches
        records = [WalletEntryRecord(wallet="INSIDER_X", chain="solana", token=f"t{i}",
                                     entry_lead_minutes=25.0 + i, early_entry=True,
                                     in_funding_cluster=True)
                   for i in range(5)]
        clusters = cl.cluster(records)
        rep_prof = rep_db.lookup("INSIDER_X", "solana")

        print("=== SFC Memecoin Phase 3 smoke test ===")
        print(f"\nSocial organity:")
        print(f"  ORGANIC_COIN : organicity {organic.organicity_score} ({organic.label})")
        print(f"  BOT_COIN     : organicity {bot.organicity_score} ({bot.label})  [{bot.reasons}]")
        print(f"\nNarrative velocity:")
        print(f"  {nv.velocity_label} | velocity {nv.velocity} | confirm {nv.cross_domain_confirmations} domain(s): {nv.confirming_domains}")
        print(f"\nTemporal insider cluster:")
        print(f"  {clusters[0].summary()}")

        # assertions
        assert organic.label == "ORGANIC", "organic token should be ORGANIC"
        assert bot.label == "ARTIFICIAL", "bot token should be ARTIFICIAL"
        assert clusters[0].is_reputed_insider, "early-entry wallet should be reputed insider"
        assert rep_prof is not None and rep_prof.role_tag == "insider", "insider profile persisted to SQLite"
        assert nv.cross_domain_confirmations >= 2, "cross-domain confirmation should fire"
        print("\n=== PASS: Phase 3 social/narrative/temporal-reputation all correct ===")
        rep_db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
