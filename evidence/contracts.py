"""Shared dataclasses for evidence consumed/across engines (spec §3).

Keeps data sources (producers) decoupled from engines (consumers): a producer
writes evidence into these contracts, an engine reads them. Neither imports the
other's engine module, preserving the Measurement Contract layering.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContractRiskInput:
    """EV-002 evidence: contract risk, produced by honeypot_sim."""
    source: str
    risk_score: float = 0.0          # 0 (safe) .. 1 (critical)
    risk_level: str = "UNKNOWN"      # SAFE / WATCH / RISKY / CRITICAL
    is_honeypot: bool = False
    findings: list[str] = field(default_factory=list)
