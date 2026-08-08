#!/usr/bin/env python3
"""Phase 1 gate smoke test on a labeled sample.

Verifies the Security Gate end-to-end rejects known-bad tokens and admits
known-good ones. This is a SMOKE test (does it run + basic correctness), NOT
a calibration — thresholds remain ILLUSTRATIVE until walk-forward validation.

Run: .venv/bin/python scripts/smoke_phase1.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_sources.honeypot_sim import ContractFacts, honeypot_risk
from engines.security_gate import SecurityGate
from engines.dev_dna import DevDNAMatcher
from engines.larp import LarpDetector, LarpSignals
from reputation.actor_reputation import ActorReputationDB

# Labeled sample: known-bad vs known-good (illustrative fixtures for smoke test).
# In production these come from backtest/labeler.py + real historical data.

def main() -> int:
    rep = ActorReputationDB()
    # Known-bad dev: 20 launches, 18 rugged, 15 LP removals -> HARD BLOCK
    rep.register_dev("devRug", "bsc", launches=20, successful=1, rugged=18,
                     abandoned=1, lps_removed=15)
    # Known-good dev
    rep.register_dev("devClean", "solana", launches=12, successful=9, rugged=1,
                     lps_removed=0)

    gate = SecurityGate(reputation=rep)
    dev_dna = DevDNAMatcher(rep)
    larp = LarpDetector()

    cases = [
        # (name, chain, deployer, ContractFacts, larp_signals, expect_blocked)
        ("RUG_HONEYPOT", "bsc", "devRug",
         ContractFacts(address="0xA", chain="bsc", sell_sellable=False, lp_total_removed=True),
         LarpSignals(fake_dev_identity=True), True),
        ("RUG_DEV", "bsc", "devRug",
         ContractFacts(address="0xB", chain="bsc"),
         LarpSignals(), True),
        ("HONEYPOT_TAX", "bsc", "unknown",
         ContractFacts(address="0xC", chain="bsc", sell_tax_pct=35.0),
         LarpSignals(), True),
        ("LARP_BOT", "solana", "unknown",
         ContractFacts(address="0xD", chain="solana"),
         LarpSignals(fake_dev_identity=True, no_original_contract=True, bot_social_presence=True),
         False),  # LARP is soft at gate (not hard-block)
        ("CLEAN_GOOD", "solana", "devClean",
         ContractFacts(address="0xE", chain="solana"),
         LarpSignals(), False),
    ]

    print("=== SFC Memecoin Phase 1 Security Gate smoke test ===")
    print(f"{'case':<14}{'contract':<12}{'dev':<12}{'larp':<8}{'blocked':<9}expected")
    print("-" * 68)
    n_ok = 0
    for name, chain, deployer, facts, lsignals, expect in cases:
        ev002 = honeypot_risk(facts)
        lres = larp.detect(lsignals)
        # gate-level LARP boolean (soft)
        decision = gate.evaluate(name, chain, ev002, deployer=deployer,
                                 larp=lres.is_larp, actor_profile=None)
        blocked = decision.blocked
        match = (blocked == expect)
        n_ok += match
        print(f"{name:<14}{ev002.risk_level:<12}{'Y' if blocked else '-':<12}"
              f"{'Y' if lres.is_larp else '-':<8}{str(blocked):<9}{expect}  {'OK' if match else 'MISMATCH'}")
        if not match:
            print("    hard_reasons:", decision.hard_reasons)

    print("-" * 68)
    print(f"PASS {n_ok}/{len(cases)}")
    return 0 if n_ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
