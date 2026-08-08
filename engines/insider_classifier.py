"""Insider P3 — ML classifier on labeled outcomes + behavioral similarity.

P3 (spec roadmap Phase 5) upgrades insider detection to an outcome-trained
classifier. It combines:
  1. the calibrated logistic model (P2, insider_prob_calib.py) for the per-token
     probability, AND
  2. behavioral similarity across launches (a wallet whose current feature
     vector resembles past CONFIRMED insider launches gets boosted).

This is the final insider layer: a classification decision (insider / not)
driven by historical outcomes, not rules.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from engines.insider_prob_calib import LogisticInsiderModel


@dataclass
class LaunchFeatures:
    """Feature vector for one launch/token a wallet participated in."""
    token: str
    wallet: str
    early_entry: float = 0.0
    funding_cluster: float = 0.0
    ita: float = 0.0
    distribution: float = 0.0
    lead_norm: float = 0.0
    outcome_insider: bool = False   # label: confirmed insider after the fact

    def vector(self) -> list[float]:
        return [self.early_entry, self.funding_cluster, self.ita,
                self.distribution, self.lead_norm]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


@dataclass
class InsiderClassification:
    wallet: str
    token: str
    probability: float = 0.0
    is_insider: bool = False
    similarity_boost: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "wallet": self.wallet,
            "token": self.token,
            "probability": round(self.probability, 3),
            "is_insider": self.is_insider,
            "similarity_boost": round(self.similarity_boost, 3),
            "reasons": self.reasons,
        }


class InsiderMLClassifier:
    """Outcome-trained insider classifier (P3)."""

    def __init__(self, model: LogisticInsiderModel | None = None,
                 decision_threshold: float = 0.5) -> None:
        self.model = model
        self.decision_threshold = decision_threshold
        self._labeled_pool: list[LaunchFeatures] = []  # confirmed-insider examples

    def register_labeled(self, launches: list[LaunchFeatures]) -> None:
        """Register historically-confirmed examples for similarity reference."""
        self._labeled_pool = [l for l in launches if l.outcome_insider]

    def fit(self, labeled: list[LaunchFeatures], *, epochs: int = 2000) -> None:
        """Train the underlying logistic model on labeled outcomes."""
        from engines.insider_prob_calib import InsiderSample
        samples = [InsiderSample(l.vector(), int(l.outcome_insider)) for l in labeled]
        self.model = LogisticInsiderModel().fit(samples, epochs=epochs)
        self.register_labeled(labeled)
        return self

    def classify(self, wallet: str, token: str, features: LaunchFeatures) -> InsiderClassification:
        res = InsiderClassification(wallet=wallet, token=token)
        if self.model is None or not self.model.fitted:
            res.reasons.append("model_unfitted_default_low")
            res.is_insider = False
            return res

        prob = self.model.predict_proba(features.vector())
        # similarity to past confirmed insider launches
        sim = 0.0
        if self._labeled_pool:
            sim = max(_cosine(features.vector(), ref.vector()) for ref in self._labeled_pool)
        res.similarity_boost = sim
        # blend: probability primary, similarity as bounded boost
        final = min(1.0, prob + 0.2 * sim)
        res.probability = round(final, 3)
        res.is_insider = final >= self.decision_threshold
        if res.is_insider:
            res.reasons.append(f"prob_{prob:.2f}_sim_{sim:.2f}")
        return res
