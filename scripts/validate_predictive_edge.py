#!/usr/bin/env python3
"""Validate whether the screener's score predicts meme-coin OUTCOME (edge test).

The user's calibration doctrine: an honest predictive-edge claim requires
score -> outcome, not just fit -> outcome. This script runs that test on the
labeled dataset (labeled_dataset_v4_large.json, n=122, price-based outcomes
rugged/survived/pumped).

CRITICAL DATA LIMITATION (stated honestly, not hidden):
  The labeled dataset only carries GMGN *trending* features in its `note`
  strings (holder_count, bundler_rate, sniper_count, dev_team_hold_rate,
  rug_ratio, entrapment_ratio, renounced_mint, is_honeypot, ...). It does NOT
  carry the live features used by score_token() (OKX holder composition,
  funding clusters, GMGN market_stats wallet tags). So this script computes a
  HISTORICAL PROXY of the core weights (organic/safety/alpha) from the features
  that ARE present, and measures whether that proxy separates rugged from
  survived/pumped. It cannot run the full live pipeline on historical tokens —
  that data was not collected at launch time.

Metrics:
  - AUC (rank) of each score vs "rugged" and vs "pumped" (0.5 = coin flip).
  - Pearson correlation of score vs final_return_pct.
  - Temporal walk-forward: sort by launch, train on early chunk, test on later;
    does the sign/discrimination of a score hold out-of-time?

Usage:
  .venv/bin/python scripts/validate_predictive_edge.py [--ds data/*.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VERDICT_GOOD_AUC = 0.60  # need >= this on BOTH rugged-sep and pumped-sep


def auc_rank(y_true: list[int], y_score: list[float]) -> float:
    """Mann-Whitney U / rank AUC. 0.5 = no better than chance."""
    n = len(y_true)
    n_pos = sum(y_true)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    idx = sorted(range(n), key=lambda i: -y_score[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and y_score[idx[j + 1]] == y_score[idx[i]]:
            j += 1
        # highest score (smallest 0-based index) gets the largest rank (n)
        avg = n - (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[idx[k]] = avg
        i = j + 1
    pos_ranks = sum(ranks[i] for i in range(n) if y_true[i])
    return (pos_ranks - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / (dx * dy or 1e-12)


def parse_note(note: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in (note or "").split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        v = v.strip()
        try:
            if v.lower() in ("true", "1"):
                out[k] = 1.0
            elif v.lower() in ("false", "0", ""):
                out[k] = 0.0
            else:
                out[k] = float(v)
        except ValueError:
            continue
    return out


def historical_proxy(note: str | None) -> dict[str, float]:
    """Compute core-weight PROXY from features present in the historical note.

    Mirrors _map_core_weights/_map_alpha_raw intent using only what the labeled
    dataset recorded at the time. Insider/OKX/funding paths are NOT present here
    and are reported as unavailable (the honest limitation).
    """
    f = parse_note(note)
    holders = f.get("holder_count", 0)
    bundler = f.get("bundler_rate", 0)
    dev = f.get("dev_team_hold_rate", 0)
    rug = f.get("rug_ratio", 0)
    entrap = f.get("entrapment_ratio", 0)
    sniper = f.get("sniper_count", 0)

    organic = 50 + (holders / 1e5) * 10 - bundler * 40 - dev * 30 - rug * 20 - entrap * 15
    organic = max(20.0, min(100.0, organic))
    safety = 20.0 if f.get("is_honeypot") else 50.0
    if f.get("renounced_mint"):
        safety += 25.0
    safety = min(100.0, safety)
    alpha = 50.0  # no volume/momentum in historical notes -> neutral
    raa = alpha * (1.0 - max(0.0, (100.0 - safety) / 100.0) * 0.6)
    return {"organic": organic, "safety": safety, "alpha": alpha, "raa": raa,
            "holders": holders, "bundler": bundler, "sniper": sniper,
            "rug": rug, "dev": dev, "entrap": entrap}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="data/labeled_dataset_v4_large.json")
    ap.add_argument("--snapshots", default="",
                    help="path to a launch-snapshot ledger (data/launch_snapshots.json); "
                         "re-scores stored full features against backfilled outcomes "
                         "(the REAL score->outcome test). Overrides --ds.")
    args = ap.parse_args()

    if args.snapshots:
        return _run_snapshot_validation(args.snapshots)

    ds = json.load(open(args.ds))
    samples = ds["samples"]

    rows = []
    for s in samples:
        sc = historical_proxy(s.get("note"))
        rows.append({"outcome": s["outcome"], "final": float(s["final_return_pct"]),
                     "launch": s.get("launch", ""), **sc})

    n = len(rows)
    counts = Counter(r["outcome"] for r in rows)
    print(f"Dataset: {args.ds}  n={n}  outcomes={dict(counts)}")
    print(f"\nData limitation: labeled dataset only has GMGN-trending features "
          f"(no OKX/funding/market_stats live snapshot) -> this tests a HISTORICAL "
          f"proxy of core weights, not the full live pipeline.\n")

    y_rugged = [1 if r["outcome"] == "rugged" else 0 for r in rows]
    y_pumped = [1 if r["outcome"] == "pumped" else 0 for r in rows]

    print("DISKRIMINASI SKOR -> OUTCOME (AUC; 0.5 = tebak, 1.0 = sempurna)")
    print(f"{'score':<10}{'AUC(rug)':<10}{'AUC(pump)':<10}  rugged_sep  pumped_sep  verdict")
    print("-" * 72)
    for name in ["organic", "safety", "alpha", "raa", "holders", "bundler",
                 "sniper", "rug"]:
        sc = [r[name] for r in rows]
        a_r = auc_rank(y_rugged, sc)
        a_p = auc_rank(y_pumped, sc)
        sep_r, sep_p = 1 - a_r, a_p  # low score->rugged, high->pumped
        if name in ("organic", "safety", "alpha", "raa"):
            verdict = "GOOD" if (sep_r >= VERDICT_GOOD_AUC and sep_p >= VERDICT_GOOD_AUC) \
                else ("WEAK" if (sep_r > 0.5 or sep_p > 0.5) else "NONE")
        else:
            verdict = ""
        print(f"{name:<10}{a_r:<10.3f}{a_p:<10.3f}  {sep_r:<11.3f}{sep_p:<11.3f}{verdict}")

    print("\nKORELASI SKOR vs final_return_pct")
    for name in ["organic", "safety", "alpha", "raa"]:
        xs = [r[name] for r in rows]
        ys = [r["final"] for r in rows]
        print(f"  {name:<8} Pearson={pearson(xs, ys):+.3f}")

    # Temporal walk-forward (no look-ahead): sort by launch, split early/late,
    # check the rugged-separation sign holds out-of-time.
    try:
        sorted_rows = sorted(rows, key=lambda r: r["launch"])
    except Exception:
        sorted_rows = rows
    half = max(1, n // 2)
    early, late = sorted_rows[:half], sorted_rows[half:]
    print(f"\nWALK-FORWARD temporal (early n={len(early)}, late n={len(late)}, "
          f"no look-ahead)")
    for name in ["organic", "raa", "sniper"]:
        def sep(rows_):
            y = [1 if r["outcome"] == "rugged" else 0 for r in rows_]
            sc = [r[name] for r in rows_]
            return 1 - auc_rank(y, sc)
        se, sl = sep(early), sep(late)
        stable = (se > 0.5) == (sl > 0.5)
        print(f"  {name:<8} early_sep={se:.3f} late_sep={sl:.3f} "
              f"sign_consistent={stable}")

    # Overall verdict (honest)
    any_good = False
    for name in ["organic", "safety", "raa"]:
        sc = [r[name] for r in rows]
        sep_r, sep_p = 1 - auc_rank(y_rugged, sc), auc_rank(y_pumped, sc)
        if sep_r >= VERDICT_GOOD_AUC and sep_p >= VERDICT_GOOD_AUC:
            any_good = True
    print("\n" + "=" * 72)
    if any_good:
        print("VERDICT: SUPPORTED — a core-weight proxy separates outcome "
              "(but note it is a historical proxy, not the full live pipeline).")
    else:
        print("VERDICT: NO EVIDENCE OF PREDICTIVE EDGE on available features.")
        print("  Score components measurable from historical notes are ~coin-flip")
        print("  (AUC ~0.5, corr ~0). Do NOT claim the model predicts meme-coin")
        print("  outcomes until a score->outcome test on live-feature snapshots")
        print("  passes. Insider/OKX/funding paths are untested here (data absent).")
    print("=" * 72)
    return 0


def _run_snapshot_validation(path: str) -> int:
    """The REAL score->outcome test on launch snapshots.

    Re-runs the full pipeline (score_token) on the stored TokenFeatures and
    measures whether the score separates the backfilled outcomes. Unlike the
    historical-proxy path, this uses the actual live features (OKX/funding/
    market_stats/wallet analytics) the model would see — so it is a genuine
    predictive-edge test, not a proxy. Requires the ledger to have backfilled
    outcomes (scripts/backfill_outcomes.py).
    """
    import json
    from pipeline import ScreeningPipeline
    from snapshot_store import deserialize_features

    try:
        ledger = json.load(open(path))
    except FileNotFoundError:
        print(f"snapshot ledger not found: {path}", file=sys.stderr)
        return 1
    records = ledger["records"]
    labeled = [r for r in records if r.get("outcome")]
    pending = len(records) - len(labeled)
    print(f"Snapshot ledger: {path}")
    print(f"  total records: {len(records)}  labeled: {len(labeled)}  "
          f"pending-backfill: {pending}")
    if len(labeled) < 21:
        print("  Not enough labeled snapshots for a meaningful test; run "
              "scripts/backfill_outcomes.py after the observation window.\n")
        return 0

    pipe = ScreeningPipeline()
    rows = []
    for r in labeled:
        features = deserialize_features(r["features"])
        try:
            s = pipe.score_token(features)
        except Exception as e:
            print(f"  [{r['token'][:10]}] rescore error: {e}")
            continue
        rows.append({"token": r["token"], "outcome": r["outcome"],
                     "score": s.risk_adjusted_alpha,
                     "confidence": s.confidence,
                     "insider": s.insider_probability,
                     "final": r.get("final_return_pct", 0.0)})

    if len(rows) < 21:
        print("  Too few re-scorable labeled snapshots; insufficient.\n")
        return 0
    counts = Counter(r["outcome"] for r in rows)
    print(f"  re-scored: {len(rows)}  outcomes={dict(counts)}\n")

    y_rugged = [1 if r["outcome"] == "rugged" else 0 for r in rows]
    y_pumped = [1 if r["outcome"] == "pumped" else 0 for r in rows]

    print("DISKRIMINASI SKOR -> OUTCOME (AUC; 0.5 = tebak, 1.0 = sempurna)")
    print(f"{'score':<12}{'AUC(rug)':<10}{'AUC(pump)':<10}  rugged_sep  pumped_sep  verdict")
    print("-" * 74)
    for name, key in [("RAA", "score"), ("Confidence", "confidence"),
                      ("Insider", "insider")]:
        sc = [r[key] for r in rows]
        a_r = auc_rank(y_rugged, sc)
        a_p = auc_rank(y_pumped, sc)
        sep_r, sep_p = 1 - a_r, a_p
        verdict = "GOOD" if (sep_r >= VERDICT_GOOD_AUC and sep_p >= VERDICT_GOOD_AUC) \
            else ("WEAK" if (sep_r > 0.5 or sep_p > 0.5) else "NONE")
        print(f"{name:<12}{a_r:<10.3f}{a_p:<10.3f}  {sep_r:<11.3f}{sep_p:<11.3f}{verdict}")

    # correlation of score with final return
    xs = [r["score"] for r in rows]
    ys = [r["final"] for r in rows]
    print(f"\nRAA vs final_return_pct  Pearson={pearson(xs, ys):+.3f}")

    print("\n" + "=" * 74)
    any_good = False
    for key in ["score", "confidence", "insider"]:
        sc = [r[key] for r in rows]
        if (1 - auc_rank(y_rugged, sc)) >= VERDICT_GOOD_AUC and \
           auc_rank(y_pumped, sc) >= VERDICT_GOOD_AUC:
            any_good = True
    if any_good:
        print("VERDICT: SUPPORTED — the pipeline score separates outcome on live-")
        print("feature snapshots. (Empirical predictive edge evidence present.)")
    else:
        print("VERDICT: NO EVIDENCE OF PREDICTIVE EDGE on live-feature snapshots.")
        print("  Score components are ~coin-flip (AUC ~0.5). Keep collecting")
        print("  snapshots; do not claim edge until a good-separation pass.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
