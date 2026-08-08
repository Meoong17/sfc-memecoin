"""Walk-forward re-validation harness (Phase 0 skeleton).

DOCTRINE (plan §8): no threshold/formula change goes to production until it
passes walk-forward re-validation on labeled historical outcomes. This skeleton
provides:
  - an expandable-window walk-forward split (train on past, test on future),
  - a generic per-fold performance summary,
  - a stub for the actual metric/evaluator (wired per-phase).

The `evaluator` callback maps a (train, test) labeled split to a float score
(e.g. threshold precision/recall on the 'rugged' class). Higher is better.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from backtest.labeler import LabeledDataset, LabeledToken


# An evaluator scores a split. Signature: evaluator(train, test) -> metric in [0,1].
Evaluator = Callable[[Sequence[LabeledToken], Sequence[LabeledToken]], float]


@dataclass
class FoldResult:
    fold_index: int
    train_n: int
    test_n: int
    score: float
    split_point: int | None = None

    def summary(self) -> dict:
        return {
            "fold_index": self.fold_index,
            "train_n": self.train_n,
            "test_n": self.test_n,
            "score": round(self.score, 4),
        }


@dataclass
class WalkForwardResult:
    results: list[FoldResult] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def summary(self) -> dict:
        return {
            "folds": len(self.results),
            "mean_score": round(self.mean_score, 4),
            "per_fold": [r.summary() for r in self.results],
        }


def walk_forward(
    dataset: LabeledDataset,
    evaluator: Evaluator,
    *,
    min_train: int = 20,
    step: int = 10,
    horizon: int = 10,
) -> WalkForwardResult:
    """Expandable-window walk-forward split (no look-ahead).

    Sorted by launch time. Each fold trains on all samples before the test
    window start, and tests on the next `horizon` samples. Window expands.
    """
    samples = sorted(dataset.samples, key=lambda t: t.launch_ts)
    n = len(samples)
    result = WalkForwardResult()
    if n < min_train + 1:
        return result  # too few samples

    start = min_train
    fold_idx = 0
    while start < n:
        train = samples[:start]
        end = min(start + horizon, n)
        test = samples[start:end]
        if not train or not test:
            break
        score = evaluator(train, test)
        result.results.append(FoldResult(
            fold_index=fold_idx,
            train_n=len(train),
            test_n=len(test),
            score=score,
            split_point=start,
        ))
        fold_idx += 1
        start += step
        # guard against infinite loop when horizon exceeds available
        if start >= n:
            break
    return result
