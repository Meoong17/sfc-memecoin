"""Normalization utilities for evidence values.

Used by the Measurement Contract so each producer normalizes consistently.
Supported modes (config/thresholds.py):
  - "zscore": (x - mean) / std  -> unbounded, centered
  - "minmax": (x - min) / (max - min)  -> [0,1] from live min/max
  - "bounded": clip to [0,1] (for already-0..1 evidence like risk scores)
  - "cluster": for funding-graph cluster metrics — clipped ratio, [0,1]
"""
from __future__ import annotations

from typing import Iterable, Sequence

from config import thresholds as TH


class NormalizationError(ValueError):
    pass


def zscore(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return (value - mean) / std


def minmax(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)


def bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def cluster(value: float) -> float:
    """Cluster overlap ratio -> [0,1]. Values may exceed 1 (dense clusters) — clipped."""
    return bounded(value)


def normalize(value: float, mode: str, *, mean: float = 0.0, std: float = 1.0,
              lo: float = 0.0, hi: float = 1.0) -> float:
    """Dispatch normalization by mode string (matches Evidence.normalization)."""
    mode = (mode or "zscore").lower()
    if mode == TH.NORM_Z:
        return zscore(value, mean, std)
    if mode == TH.NORM_MINMAX:
        return minmax(value, lo, hi)
    if mode == TH.NORM_BOUNDED:
        return bounded(value)
    if mode == "cluster":
        return cluster(value)
    raise NormalizationError(f"Unknown normalization mode: {mode}")


def normalize_series(values: Sequence[float], mode: str) -> list[float]:
    """Normalize a whole series; zscore/minmax use series statistics."""
    n = len(values)
    if n == 0:
        return []
    mode = (mode or "zscore").lower()
    if mode == TH.NORM_Z:
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        std = var ** 0.5
        return [zscore(v, mean, std) for v in values]
    if mode == TH.NORM_MINMAX:
        lo, hi = min(values), max(values)
        return [minmax(v, lo, hi) for v in values]
    if mode in (TH.NORM_BOUNDED, "cluster"):
        return [bounded(v) for v in values]
    raise NormalizationError(f"Unknown normalization mode: {mode}")


def normalize_dict(values: dict[str, float], mode: str) -> dict[str, float]:
    """Convenience for dict of metric -> normalized value."""
    out = dict(values)
    for k, v in values.items():
        if isinstance(v, (int, float)):
            out[k] = normalize(v, mode)
    return out


__all__ = ["zscore", "minmax", "bounded", "cluster", "normalize",
           "normalize_series", "normalize_dict", "NormalizationError"]

