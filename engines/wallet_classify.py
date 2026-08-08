"""Wallet Classification Engine (spec §6.5) — 11-role taxonomy.

Classifies each wallet into ONE role before insider metrics are computed, to
avoid conflating "all profitable wallets = insider".

Roles (spec §6.5 + roadmap): Dev, Insider, Smart Money, Sniper, Bundler, KOL,
Market Maker, Arbitrage, Public, Sybil, Unknown.

Accuracy depends on behavioral thresholds NOT yet calibrated (spec §6.5 note).
These are rule-based heuristics, flagged ILLUSTRATIVE — see docs/CALIBRATION.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Role constants
ROLE_DEV = "dev"
ROLE_INSIDER = "insider"
ROLE_SMART_MONEY = "smart_money"
ROLE_SNIPER = "sniper"
ROLE_BUNDLER = "bundler"
ROLE_KOL = "kol"
ROLE_MM = "market_maker"
ROLE_ARBITRAGE = "arbitrage"
ROLE_PUBLIC = "public"
ROLE_SYBIL = "sybil"
ROLE_UNKNOWN = "unknown"

ALL_ROLES = [
    ROLE_DEV, ROLE_INSIDER, ROLE_SMART_MONEY, ROLE_SNIPER, ROLE_BUNDLER,
    ROLE_KOL, ROLE_MM, ROLE_ARBITRAGE, ROLE_PUBLIC, ROLE_SYBIL, ROLE_UNKNOWN,
]


@dataclass
class WalletSignals:
    """Behavioral signals for a single wallet."""
    wallet: str
    is_deployer: bool = False
    in_funding_cluster: bool = False
    entry_lead_seconds: float = 0.0        # how early vs public info expansion
    first_buy_at_launch_ms: float = float("inf")  # ms after launch
    buy_before_info_expansion: bool = False
    buys_coordinated: bool = False          # part of group buy via funding cluster
    high_win_rate: float = 0.0              # [0,1]
    high_social_influence: float = 0.0      # [0,1]
    high_frequency: float = 0.0             # trades/day
    in_organic_holder_set: bool = False
    flagged_sybil: bool = False


@dataclass
class Classification:
    wallet: str
    role: str = ROLE_UNKNOWN
    confidence: float = 0.5
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "wallet": self.wallet,
            "role": self.role,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
        }


# ILLUSTRATIVE thresholds (calibration doctrine).
_SNIPER_MAX_LAUNCH_MS = 3_000       # sniper buys within ~3s of launch
_INSIDER_LEAD_SEC = 120.0           # insider enters >120s before public info
_SMART_MONEY_MIN_WIN = 0.6
_KOL_MIN_SOCIAL = 0.7
_MM_MIN_FREQ = 50.0


class WalletClassifier:
    """Rule-based 11-role classifier. Order of precedence matters."""

    def classify(self, sig: WalletSignals) -> Classification:
        c = Classification(wallet=sig.wallet)

        # 1. Dev
        if sig.is_deployer:
            c.role, c.confidence = ROLE_DEV, 0.95
            c.reasons.append("deployer")
            return c

        # 2. Insider: entered before public info expansion
        if sig.buy_before_info_expansion and sig.entry_lead_seconds > _INSIDER_LEAD_SEC:
            c.role, c.confidence = ROLE_INSIDER, 0.8
            c.reasons.append(f"early_entry_lead_{sig.entry_lead_seconds:.0f}s")
            return c

        # 3. Sybil
        if sig.flagged_sybil and not sig.in_organic_holder_set:
            c.role, c.confidence = ROLE_SYBIL, 0.85
            c.reasons.append("flagged_sybil")
            return c

        # 4. Bundler: coordinated buy via funding cluster near launch
        if sig.buys_coordinated and sig.in_funding_cluster and sig.first_buy_at_launch_ms < _SNIPER_MAX_LAUNCH_MS:
            c.role, c.confidence = ROLE_BUNDLER, 0.8
            c.reasons.append("coordinated_cluster_buy")
            return c

        # 5. Sniper: very close to launch
        if sig.first_buy_at_launch_ms < _SNIPER_MAX_LAUNCH_MS:
            c.role, c.confidence = ROLE_SNIPER, 0.75
            c.reasons.append(f"launch_buy_{sig.first_buy_at_launch_ms:.0f}ms")
            return c

        # 6. KOL: high social influence + wallet activity
        if sig.high_social_influence >= _KOL_MIN_SOCIAL:
            c.role, c.confidence = ROLE_KOL, 0.7
            c.reasons.append("high_social_influence")
            return c

        # 7. Smart Money: profitable + not too frequent
        if sig.high_win_rate >= _SMART_MONEY_MIN_WIN and sig.high_frequency < _MM_MIN_FREQ:
            c.role, c.confidence = ROLE_SMART_MONEY, 0.7
            c.reasons.append("high_win_rate")
            return c

        # 8. Market Maker: very high frequency
        if sig.high_frequency >= _MM_MIN_FREQ:
            c.role, c.confidence = ROLE_MM, 0.7
            c.reasons.append("high_frequency")
            return c

        # 9. Arbitrage: frequent + moderate — placeholding; refine in later phase
        # 10. Public: organic holder set, no special signals
        if sig.in_organic_holder_set:
            c.role, c.confidence = ROLE_PUBLIC, 0.6
            c.reasons.append("organic_holder")
            return c

        # 11. Unknown
        c.role = ROLE_UNKNOWN
        c.confidence = 0.4
        return c
