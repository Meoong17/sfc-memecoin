# CALIBRATION — Live Ledger

Doktrin (plan §8): **tidak ada threshold/formula produksi tanpa walk-forward
re-validation pada outcome historis berlabel** (rugged / survived / pumped).
Setiap perubahan threshold dicatat di sini dengan bukti empiris.

Status saat ini: **Phase 0** — seluruh threshold masih `calibrated=False`
(ILLUSTRATIVE) dan TIDAK ditegakkan di produksi oleh `VetoEvaluator`.

## Threshold belum dikalibrasi (dari config/thresholds.py)

| Threshold | Nilai | Status | Bukti |
|---|---|---|---|
| ihr_low_max | 0.05 | ILLUSTRATIVE | belum ada |
| ihr_moderate_max | 0.10 | ILLUSTRATIVE | belum ada |
| ihr_high_max | 0.20 | ILLUSTRATIVE | belum ada |
| ihr_critical_min | 0.20 | ILLUSTRATIVE | belum ada |
| insider_prob_soft_veto | 0.80 | ILLUSTRATIVE | belum ada |
| exit_liquidity_levels | LOW/MED/HIGH | ILLUSTRATIVE | belum ada |

## Riwayat perubahan

(Tanggal — threshold — nilai lama → baru — justifikasi empiris)

## Prosedur menandai threshold sebagai validated

1. Kumpulkan `LabeledDataset` dari outcome historis (backtest/labeler.py).
2. Jalankan `walk_forward` dengan evaluator metrik sasaran (mis. presisi/recall kelas `rugged`).
3. Catat mean_score + distribusi per-fold di sini.
4. Baru set `calibrated=True` pada threshold terkait + tanggal.
