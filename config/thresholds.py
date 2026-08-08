"""Central threshold registry.

DOCTRINE: every threshold ships with `calibrated=False` (ILLUSTRATIVE) until it
passes walk-forward re-validation on labeled historical outcomes. Production
gates MUST refuse to enforce any threshold that is not calibrated. See
docs/CALIBRATION.md for the live ledger.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Threshold:
    """A tunable threshold with a calibration gate."""
    name: str
    value: float
    calibrated: bool = False
    note: str = ""
    domain: tuple[float, float] | None = None  # expected output range


# --- Insider Holding Risk bands (spec §6.6.4) ---
IHR_BANDS = [
    Threshold("ihr_low_max", 0.05, calibrated=False, domain=(0.0, 1.0), note="IHR <5% LOW"),
    Threshold("ihr_moderate_max", 0.10, calibrated=False, domain=(0.0, 1.0), note="5-10% MODERATE"),
    Threshold("ihr_high_max", 0.20, calibrated=False, domain=(0.0, 1.0), note="10-20% HIGH"),
    # >0.20 => CRITICAL

    # --- Insider soft veto (spec §4) ---
    Threshold("insider_prob_soft_veto", 0.80, calibrated=False, domain=(0.0, 1.0), note="Soft veto if prob >80% AND hold CRITICAL"),

    # --- Veto: IHR classification boundary for CRITICAL ---
    Threshold("ihr_critical_min", 0.20, calibrated=False, domain=(0.0, 1.0), note=">=20% CRITICAL"),
]

# Exit Liquidity Risk: LOW / MED / HIGH categorical (no numeric band yet).
EXIT_LIQUIDITY_LEVELS = ("LOW", "MED", "HIGH")

# --- Normalization defaults ---
NORM_Z = "zscore"
NORM_MINMAX = "minmax"
NORM_BOUNDED = "bounded"  # clip to [0,1]

# --- Confidence defaults (spec §7) ---
DEFAULT_DQI_FLOOR = 0.5  # tokens below this completeness/quality floor are dropped


def get(name: str) -> Threshold:
    for t in IHR_BANDS:
        if t.name == name:
            return t
    raise KeyError(f"Unknown threshold: {name}")


def uncalibrated_names() -> list[str]:
    """Return names of all thresholds not yet validated."""
    return [t.name for t in IHR_BANDS if not t.calibrated]
