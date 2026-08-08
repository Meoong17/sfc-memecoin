#!/usr/bin/env python3
"""Analyze insider-feature stability on a labeled dataset (calibration step d).

Parses each sample's `note` string (key=value; ...) into numeric features,
computes per-feature Pearson correlation against final_return_pct and the
per-outcome means, and reports which candidate insider features are stable
across the dataset. This is the empirical check on whether features like
`twitter_create_token_count` (corr +0.921 on v3) hold up at larger n.

Usage:
  .venv/bin/python scripts/analyze_features.py [--ds data/*.json] [--top N]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pearson_ci(xs: list[float], ys: list[float], n_boot: int = 2000,
               seed: int = 0) -> tuple[float, float, float]:
    """Return (corr, ci_low, ci_high) via non-parametric bootstrap."""
    random.seed(seed)
    n = len(xs)
    if n < 3:
        return 0.0, 0.0, 0.0
    corrs = []
    for _ in range(n_boot):
        idx = [random.randrange(n) for _ in range(n)]
        bx = [xs[i] for i in idx]
        by = [ys[i] for i in idx]
        if len(set(bx)) < 2 or len(set(by)) < 2:
            continue
        corrs.append(pearson(bx, by))
    corrs.sort()
    c = pearson(xs, ys)
    lo = corrs[int(0.025 * len(corrs))] if corrs else c
    hi = corrs[int(0.975 * len(corrs)) - 1] if corrs else c
    return c, lo, hi


def split_corr(xs: list[float], ys: list[float], n_split: int = 5,
               seed: int = 1) -> list[float]:
    """Correlation on each of n_split contiguous chunks (temporal stability)."""
    n = len(xs)
    out = []
    for i in range(n_split):
        lo = (n * i) // n_split
        hi = (n * (i + 1)) // n_split
        seg_x = xs[lo:hi]
        seg_y = ys[lo:hi]
        if len(seg_x) >= 3:
            out.append(pearson(seg_x, seg_y))
    return out


def parse_note(note: str | None) -> dict[str, float]:
    """'a=1; b=2.5' -> {'a':1.0, 'b':2.5}. Non-numeric/None -> dropped."""
    out: dict[str, float] = {}
    if not note:
        return out
    for part in note.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        v = v.strip()
        # bool-ish / int / float
        if v.lower() in ("true", "1"):
            out[k] = 1.0
            continue
        if v.lower() in ("false", "0", "none", "null", ""):
            out[k] = 0.0
            continue
        try:
            out[k] = float(v)
        except ValueError:
            continue
    return out


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sqrt(sum((x - mx) ** 2 for x in xs) or 1e-12)
    dy = sqrt(sum((y - my) ** 2 for y in ys) or 1e-12)
    return num / (dx * dy)


def spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation — robust to outliers (cross-check vs Pearson)."""
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    if len(xs) < 3:
        return 0.0
    return pearson(ranks(xs), ranks(ys))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", type=str, default="data/labeled_dataset_v3_variety.json")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    ds = json.load(open(args.ds))
    samples = ds["samples"]
    n = len(samples)
    print(f"Dataset: {args.ds}")
    print(f"  n={n}  outcomes={_counts(samples)}")

    # feature -> (list of (value, final_return, outcome))
    feats: dict[str, list[tuple[float, float, str]]] = {}
    missing_notes = 0
    for s in samples:
        vals = parse_note(s.get("note", ""))
        if not vals:
            missing_notes += 1
        for k, v in vals.items():
            feats.setdefault(k, []).append((v, float(s["final_return_pct"]), s["outcome"]))

    print(f"  samples with no parseable features: {missing_notes}/{n}")
    print(f"  distinct features parsed: {len(feats)}\n")

    rows = []
    for k, pairs in feats.items():
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        c = pearson(xs, ys)
        n_obs = len(pairs)
        # per-outcome means
        means = {}
        for oc in ("rugged", "survived", "pumped"):
            vals = [p[0] for p in pairs if p[2] == oc]
            means[oc] = (sum(vals) / len(vals)) if vals else float("nan")
        rows.append((abs(c), c, n_obs, k, means))

    rows.sort(key=lambda r: r[0], reverse=True)
    print(f"{'feat':<40} {'corr':>7} {'n':>4}   rugged   survived   pumped")
    print("-" * 78)
    for abs_c, c, n_obs, k, means in rows[: args.top]:
        def f(x):
            return "  nan  " if x != x else f"{x:8.2f}"
        print(f"{k:<40} {c:>7.3f} {n_obs:>4}   {f(means['rugged'])}   {f(means['survived'])}   {f(means['pumped'])}")

    # stability verdict on the headline insider feature
    if "twitter_create_token_count" in feats:
        # sort by launch time so split_corr is a TRUE temporal chunking
        sorted_samples = sorted(samples, key=lambda s: s.get("launch", ""))
        xs = [parse_note(s.get("note", "")).get("twitter_create_token_count", 0.0)
              for s in sorted_samples]
        ys = [float(s["final_return_pct"]) for s in sorted_samples]
        c, lo, hi = pearson_ci(xs, ys)
        splits = split_corr(xs, ys)
        rho = spearman(xs, ys)
        print("\n=== headline feature: twitter_create_token_count (temporal-sorted) ===")
        print(f"  Pearson corr = {c:+.3f}  [95% CI {lo:+.3f}, {hi:+.3f}]  n={len(xs)}")
        print(f"  Spearman (rank, robust) = {rho:+.3f}")
        print(f"  per-chunk Pearson (by launch time): {[f'{x:+.2f}' for x in splits]}")
        pos = [x for x in splits if x >= 0.5]
        stable = abs(c) >= 0.7 and abs(rho) >= 0.4 and (len(pos) / len(splits) >= 0.6 if splits else False)
        print(f"  verdict: {'STABLE' if stable else 'NOT STABLE (temporal/robust) — hypothesis only'}")
        print(f"  CI {lo:+.3f}..{hi:+.3f} {'excludes' if not (lo < 0 < hi) else 'INCLUDES 0 -> not significant'}")
    return 0


def _counts(samples: list[dict]) -> dict[str, int]:
    from collections import Counter
    return dict(Counter(s["outcome"] for s in samples))


if __name__ == "__main__":
    raise SystemExit(main())
