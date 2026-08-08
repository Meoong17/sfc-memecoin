# SFC Memecoin Screening Engine

Real-time on-chain meme-coin screener dengan **Insider Intelligence Engine** kelas satu.
Implementasi dari spec `/home/ubuntu/B/SFC_Meme_Screening_Engine_v5.docx`.

Status: **Phase 0 (formal foundation) — 52 unit test hijau.**

## Prinsip inti

- **Measurement Contract** (`evidence/registry.py`) — satu Evidence ID, banyak konsumen,
  tanpa perhitungan ulang independen. EV-021 (funding graph) dipakai bersama Wallet Graph +
  Sybil + Insider; engine yang berbagi evidence **tidak independen** → Confidence didiskon.
- **Kalibrasi empiris wajib** — semua threshold di `config/thresholds.py` ber-flag
  `calibrated=False` (ILLUSTRATIVE) sampai lolos walk-forward re-validation
  (`backtest/walk_forward.py`) pada outcome berlabel (`backtest/labeler.py`).
- **Confidence** = Eq × Ei × Completeness × Stability, lalu × DQI (spec §7).

## Struktur

```
evidence/      registry (Measurement Contract) + normalization
config/        settings (chain/API) + thresholds (semua flag ILLUSTRATIVE)
engines/       veto hierarchy (HARD/SOFT/PENALTY) — Phase 0
scoring/       confidence engine (multiplicative × DQI, overlap independence)
backtest/      labeler (outcome schema) + walk_forward (harness)
tests/         unit tests (52)
```

## Jalankan test

```bash
.venv/bin/python -m pytest tests/ -v
```

## Roadmap

Phase 0 formal foundation ✅ · Phase 1 Security/Dev/LARP/DEX/Wallet · Phase 2 Wallet Graph/Sybil/Classify/Insider P0 · Phase 3 Social/Reputation · Phase 4 Absorption/Regime/Insider P2 · Phase 5 ML ranking/Insider P3.

Lihat `docs/CALIBRATION.md` untuk ledger kalibrasi threshold.
