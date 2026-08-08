"""Backfill LabeledDataset from REAL GMGN data (calibration step c).

Builds a labeled dataset (rugged/survived/pumped) from real on-chain history:
  1. market trenches (new_creation / completed) -> token universe + created_ts
  2. market kline (1d) per token -> price series
  3. compute peak_return / max_drawdown / days_observed
  4. classify via backtest.labeler.classify_outcome

This is the empirical calibration source — the walk-forward re-validation in
backtest/walk_forward.py runs against this data (calibration doctrine).

NOTE: outcome classification here is a RULE-BASED proxy on price history
(drawdown/peak/LP). It is honest and explicit — not a claim of ground truth.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from backtest.labeler import LabeledDataset, LabeledToken, Outcome, classify_outcome
from fetchers.gmgn import GmgnFetcher


@dataclass
class BackfillConfig:
    chain: str = "solana"
    resolution: str = "1d"
    max_tokens: int = 40
    min_launch_days_ago: int = 1      # skip tokens created today (no history)
    max_launch_days_ago: int = 90     # skip ancient tokens
    # outcome thresholds (from backtest.labeler defaults; override for calibration)
    rug_max_dd_pct: float = -60.0
    pump_min_peak_pct: float = 300.0
    pump_min_hold_days: int = 7


class KlineAnalyzer:
    """Computes outcome metrics from a 1d kline series."""

    @staticmethod
    def analyze(kline_list: list[dict]) -> dict | None:
        """Return {peak_return_pct, max_drawdown_pct, days_observed} or None."""
        if not kline_list:
            return None
        closes = [float(k.get("close", 0.0)) for k in kline_list if k.get("close")]
        highs = [float(k.get("high", 0.0)) for k in kline_list if k.get("high")]
        if not closes or closes[0] <= 0:
            return None

        base = closes[0]
        peak_high = max(highs) if highs else base
        peak_return_pct = (peak_high / base - 1.0) * 100.0

        # max drawdown from running peak close
        running_peak = closes[0]
        max_dd = 0.0
        for c in closes:
            running_peak = max(running_peak, c)
            if running_peak > 0:
                dd = (c / running_peak - 1.0) * 100.0
                max_dd = min(max_dd, dd)

        return {
            "peak_return_pct": round(peak_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "days_observed": len(closes),
        }


class DatasetBackfiller:
    """Fetches real data and builds a LabeledDataset."""

    def __init__(self, gmgn: GmgnFetcher, config: BackfillConfig | None = None) -> None:
        self.gmgn = gmgn
        self.config = config or BackfillConfig()

    def _chain(self) -> str:
        return {"solana": "sol", "sol": "sol"}.get(self.config.chain, self.config.chain)

    def fetch_universe(self) -> list[dict]:
        """Fetch token universe from trenches (new_creation + completed)."""
        tokens: dict[str, dict] = {}
        for typ in ("new_creation", "completed"):
            try:
                data = self.gmgn._run("market", "trenches", "--chain", self._chain(),
                                      "--type", typ, "--limit", "80",
                                      "--sort-by", "created_timestamp", "--raw")
            except Exception as e:
                import logging
                logging.warning("trenches %s failed: %s", typ, e)
                continue
            bucket = data.get(typ) or []
            for t in bucket:
                addr = t.get("address")
                if addr:
                    tokens[addr] = t
        return list(tokens.values())

    def _launch_age_days(self, created_ts: int) -> int:
        return int((time.time() - created_ts) / 86400.0) if created_ts else 0

    def build(self, *, progress: bool = True) -> LabeledDataset:
        """Fetch kline for each token, classify outcome, build dataset."""
        ds = LabeledDataset()
        universe = self.fetch_universe()
        if progress:
            print(f"Universe: {len(universe)} tokens from trenches")

        kept = 0
        for t in universe:
            addr = t.get("address")
            if not addr:
                continue
            created = int(t.get("created_timestamp", 0) or 0)
            age = self._launch_age_days(created)
            if age < self.config.min_launch_days_ago or age > self.config.max_launch_days_ago:
                continue
            if kept >= self.config.max_tokens:
                break

            try:
                kline = self.gmgn._run("market", "kline", "--chain", self._chain(),
                                       "--address", addr,
                                       "--resolution", self.config.resolution, "--raw")
            except Exception:
                continue
            klist = (kline or {}).get("list") or []
            metrics = KlineAnalyzer.analyze(klist)
            if metrics is None:
                continue

            lp_removed = not bool(t.get("is_token_live", True)) and age > 2
            outcome = classify_outcome(
                lp_removed=lp_removed,
                max_drawdown_pct=metrics["max_drawdown_pct"],
                peak_return_pct=metrics["peak_return_pct"],
                days_observed=metrics["days_observed"],
            )
            ds.add(LabeledToken(
                token=addr, chain=self.config.chain,
                launch_ts=__import__("datetime").datetime.fromtimestamp(created or time.time()),
                outcome=outcome,
                peak_return_pct=metrics["peak_return_pct"],
                final_return_pct=metrics["max_drawdown_pct"],
                days_observed=metrics["days_observed"],
                note=f"holder_count={t.get('holder_count')}; is_honeypot={t.get('is_honeypot')}",
            ))
            kept += 1
            if progress:
                print(f"  [{kept}/{self.config.max_tokens}] {addr[:10]} {outcome.value} "
                      f"peak={metrics['peak_return_pct']:.0f}% dd={metrics['max_drawdown_pct']:.0f}%")
        return ds

    def save(self, ds: LabeledDataset, path: str) -> None:
        payload = {
            "generated_at": time.time(),
            "config": {
                "chain": self.config.chain, "resolution": self.config.resolution,
                "rug_max_dd_pct": self.config.rug_max_dd_pct,
                "pump_min_peak_pct": self.config.pump_min_peak_pct,
                "pump_min_hold_days": self.config.pump_min_hold_days,
            },
            "samples": [s.summary() for s in ds.samples],
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
