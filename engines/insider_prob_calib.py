"""Insider Probability — calibrated logistic model (Insider P2, spec roadmap).

Upgrades the P0 rule-based insider probability (insider_intel.py) to a LEARNED
logistic regression fitted on labeled historical outcomes, following the
calibration doctrine (docs/CALIBRATION.md). Pure-python gradient descent — no
extra dependency.

Features (from labeled dataset):
  1. early_entry            (0/1) — entered before public info expansion
  2. funding_cluster        (0/1) — member of a common-funder cluster
  3. ita                    [0,1] — Insider Timing Advantage
  4. insider_distribution   (0/1) — distribution detected
  5. median_lead_minutes    [0,∞) — normalized lead time

Outcome label: y=1 if the wallet was later confirmed an insider (rug/dev dump /
early-sell pattern), else 0. The model is calibrated (weights learned) from data
and only then is the probability treated as production-usable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class InsiderSample:
    features: list[float]      # [early_entry, funding_cluster, ita, distribution, lead_norm]
    label: int                 # 0/1

    @property
    def target(self) -> int:
        return self.label


@dataclass
class LogisticInsiderModel:
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    fitted: bool = False
    n_features: int = 5

    def predict_proba(self, features: list[float]) -> float:
        if not self.fitted:
            raise RuntimeError("Model not fitted; predict before fitting is invalid.")
        if len(features) != self.n_features:
            raise ValueError(f"Expected {self.n_features} features, got {len(features)}")
        z = self.bias + sum(w * x for w, x in zip(self.weights, features))
        return 1.0 / (1.0 + math.exp(-z))

    def _sigmoid(self, z: float) -> float:
        return 1.0 / (1.0 + math.exp(-z))

    def fit(self, samples: list[InsiderSample], *, lr: float = 0.1, epochs: int = 2000,
            l2: float = 0.001, tol: float = 1e-6) -> "LogisticInsiderModel":
        n = len(samples)
        if n == 0:
            raise ValueError("No training samples")
        self.n_features = len(samples[0].features)
        self.weights = [0.0] * self.n_features
        self.bias = 0.0

        prev_loss = float("inf")
        for _ in range(epochs):
            grad_w = [0.0] * self.n_features
            grad_b = 0.0
            loss = 0.0
            for s in samples:
                z = self.bias + sum(w * x for w, x in zip(self.weights, s.features))
                p = self._sigmoid(z)
                err = p - s.target
                for j in range(self.n_features):
                    grad_w[j] += err * s.features[j]
                grad_b += err
                loss += -s.target * math.log(p + 1e-9) - (1 - s.target) * math.log(1 - p + 1e-9)
            # L2
            for j in range(self.n_features):
                grad_w[j] = (grad_w[j] + l2 * self.weights[j]) / n
            grad_b /= n
            loss = loss / n
            for j in range(self.n_features):
                self.weights[j] -= lr * grad_w[j]
            self.bias -= lr * grad_b
            if abs(prev_loss - loss) < tol:
                break
            prev_loss = loss
        self.fitted = True
        return self

    def calibration_stats(self, samples: list[InsiderSample]) -> dict:
        """Brier score + accuracy on a sample set (calibration quality)."""
        if not self.fitted:
            raise RuntimeError("Not fitted")
        brier = 0.0
        correct = 0
        n = len(samples)
        for s in samples:
            p = self.predict_proba(s.features)
            brier += (p - s.target) ** 2
            correct += int((p >= 0.5) == bool(s.target))
        return {
            "n": n,
            "brier_score": round(brier / n, 4),
            "accuracy": round(correct / n, 4) if n else 0.0,
        }

    def summary(self) -> dict:
        return {
            "fitted": self.fitted,
            "n_features": self.n_features,
            "weights": [round(w, 3) for w in self.weights],
            "bias": round(self.bias, 3),
        }
