"""Insider-outcome labeling from ON-CHAIN facts (not price proxy).

This is the REAL-insider label source (v5 §8): classify a token's outcome by
the actual dev / holder / LP on-chain behaviour — rug (LP removed / honeypot),
dev-dump (creator sold off), early-sell (insider cluster dumping early) —
instead of the fragile price-proxy label in backfill.label_for_calibration.

Distinct from both `backtest.labeler.classify_outcome` (production classifier)
and `backfill.label_for_calibration` (price-based). Here the ground truth is
dev/holder/LP activity, which is what an insider detector is actually trying
to predict.

Rule (deliberately thresholded, ILLUSTRATIVE until calibrated):
  - RUG       : LP removed / honeypot / renounced-but-locked-fail / dev sold
                near-100% AND withdrew liquidity
  - DEV_DUMP  : dev sold a large share of its position (sell_amount_percentage
                high AND dev_sell_tx_count > dev_buy_tx_count)
  - EARLY_SELL: high top-10 concentration with net outflow (early insiders
                selling), no full dev dump
  - CLEAN     : everything else (no dev dump, no rug, low concentration)

Feature inputs (dict keys) — all sourced from real GMGN live endpoints:
  dev_sell_amount_percentage, dev_sell_tx_count, dev_buy_tx_count,
  dev_current_sell_amount, dev_current_transfer_out_amount,  (token traders dev)
  top_10_holder_rate, is_honeypot, renounced, lp_locked_pct,    (token security)
  rug_ratio, entrapment_ratio                                     (trending)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InsiderOutcome(str, Enum):
    RUG = "rug"
    DEV_DUMP = "dev_dump"
    EARLY_SELL = "early_sell"
    CLEAN = "clean"


@dataclass
class InsiderLabeledToken:
    token: str
    chain: str
    outcome: InsiderOutcome
    signals: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "outcome": self.outcome.value,
            "signals": {k: round(v, 4) if isinstance(v, float) else v
                        for k, v in self.signals.items()},
        }


# ILLUSTRATIVE thresholds (calibrate on labeled dev-dump/rug before enforcing).
DEV_DUMP_SELL_RATIO = 0.60     # dev sold >= this fraction of position -> dump
DEV_NET_SELLER = True          # require sell_tx > buy_tx (direction)
EARLY_SELL_TOP10 = 0.30        # top-10 concentration >= this + outflow -> early sell
TOP10_LOW = 0.10               # below this = broadly distributed -> clean-ish
RUG_LP_UNLOCKED = 0.30         # LP not locked (locked < this) near a dev dump -> rug


def classify_insider_outcome(sig: dict) -> InsiderOutcome:
    """Classify insider outcome from on-chain dev/holder/LP signals (rule-based)."""
    def f(k, d=0.0) -> float:
        v = sig.get(k)
        if v is None:
            return d
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    is_honeypot = bool(sig.get("is_honeypot"))
    renounced = bool(sig.get("renounced"))
    dev_sell_ratio = f("dev_sell_amount_percentage")
    dev_sell_tx = int(f("dev_sell_tx_count"))
    dev_buy_tx = int(f("dev_buy_tx_count"))
    dev_out = f("dev_current_transfer_out_amount")
    dev_in = f("dev_current_sell_amount")  # proxy for what dev held
    top10 = f("top_10_holder_rate")
    lp_locked = f("lp_locked_pct", 1.0)
    rug_ratio = f("rug_ratio")

    # RUG: honeypot OR dev dumped AND LP not secured (withdrew liquidity).
    # LP "secure" = burned to blackhole OR reported locked (permanent, un-withdrawable).
    lp_secure = lp_locked >= RUG_LP_UNLOCKED or bool(sig.get("lp_burned"))
    if is_honeypot:
        return InsiderOutcome.RUG
    if dev_sell_ratio >= DEV_DUMP_SELL_RATIO and not lp_secure:
        return InsiderOutcome.RUG

    # DEV_DUMP: dev sold a large share, net seller
    net_seller = dev_sell_tx > dev_buy_tx if DEV_NET_SELLER else True
    if dev_sell_ratio >= DEV_DUMP_SELL_RATIO and net_seller:
        return InsiderOutcome.DEV_DUMP

    # EARLY_SELL: high top-10 concentration + net outflow (early insiders selling)
    if top10 >= EARLY_SELL_TOP10 and dev_out > dev_in and dev_out > 0:
        return InsiderOutcome.EARLY_SELL

    return InsiderOutcome.CLEAN


def label_from_gmgn(token: str, chain: str,
                    dev_signals: dict | None, security: dict | None) -> InsiderLabeledToken:
    """Assemble an InsiderLabeledToken from raw GMGN dev + security dicts."""
    sig = dict(dev_signals or {})
    sec = security or {}
    sig["top_10_holder_rate"] = _safe(sec.get("top_10_holder_rate"))
    sig["is_honeypot"] = bool(sec.get("is_honeypot"))
    sig["renounced"] = bool(sec.get("renounced"))
    # LP safety: a blackhole/burn detail means the LP is PERMANENTLY removed to a
    # dead address (secure — cannot be withdrawn), NOT "0% locked". `lock_percent`
    # alone is misleading: burned LP reports lock_percent=0 yet is_blackhole=true.
    lock = sec.get("lock_summary") or {}
    detail = lock.get("lock_detail") or []
    burned = any(bool(d.get("is_blackhole")) for d in detail if isinstance(d, dict))
    is_locked = bool(lock.get("is_locked"))
    lp_locked = _safe(lock.get("lock_percent"), 0.0)
    # secure = burned to blackhole OR reported locked. Else take lock_percent.
    lp_secure = burned or is_locked
    sig["lp_locked_pct"] = (1.0 if lp_secure else min(1.0, lp_locked))
    sig["lp_burned"] = burned
    sig["rug_ratio"] = _safe(sec.get("rug_ratio"))
    return InsiderLabeledToken(token=token, chain=chain,
                               outcome=classify_insider_outcome(sig), signals=sig)


def _safe(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d
