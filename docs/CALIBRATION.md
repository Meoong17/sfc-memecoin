# CALIBRATION — Live Ledger

Doktrin: **tidak ada threshold/formula produksi tanpa walk-forward re-validation
pada outcome historis berlabel** (rugged / survived / pumped). Setiap perubahan
threshold dicatat di sini dengan bukti empiris.

## Status: SEMUA threshold masih ILLUSTRATIVE (calibrated=False)

Backfill pertama (2026-08) DIJALANKAN dengan data nyata GMGN, hasilnya jujur:
**data belum cukup untuk kalibrasi.** Threshold tetap ILLUSTRATIVE dan TIDAK
ditegakkan di produksi oleh `VetoEvaluator`.

### Hasil backfill nyata — v1 (data/labeled_dataset_v1.json)

- Universe: 160 token dari GMGN `market trenches` (solana).
- Hanya 3 token berusia >= 2 hari; maksimal 2 hari. Trenches = token BARU lahir.
- 20 sampel dilabeli (min-age 0). Semua `survived`, semua `dd=0%`.
- Walk-forward "mean score 1.000" = **ARTEFAK DATA HOMOGEN, BUKAN validasi.**
  Karena semua label identik, rugged-rate train==test==0 jadi "konsisten".
  Ini TIDAK membuktikan threshold apa pun.

### Kenapa belum bisa kalibrasi

| Masalah | Dampak |
|---|---|
| Trenches memberi token baru (age<=2 hari) | kline 1d cuma 1-2 baris -> tak ada horizon utk deteksi rug/pump |
| Definisi outcome butuh minggu | rugged/pumped tak bisa dideteksi dalam 2 hari |
| Threshold IHR/ITA butuh label insider | label insider = rug/dev-dump/early-sell, butuh data historis panjang |

### Threshold belum dikalibrasi (dari config/thresholds.py)

| Threshold | Nilai | Status | Bukti |
|---|---|---|---|
| ihr_low_max | 0.05 | ILLUSTRATIVE | belum ada |
| ihr_moderate_max | 0.10 | ILLUSTRATIVE | belum ada |
| ihr_high_max | 0.20 | ILLUSTRATIVE | belum ada |
| ihr_critical_min | 0.20 | ILLUSTRATIVE | belum ada |
| insider_prob_soft_veto | 0.80 | ILLUSTRATIVE | belum ada |
| exit_liquidity_levels | LOW/MED/HIGH | ILLUSTRATIVE | belum ada |
| CONTRACT_CRITICAL_SCORE (security) | 0.70 | ILLUSTRATIVE | belum ada |
| TAX_REDLINE / LP_LOCK (honeypot) | 20% / 50% | ILLUSTRATIVE | belum ada |
| IHR penalty weights (alpha_risk) | 0-0.30 | ILLUSTRATIVE | belum ada |
| sybil weights | 0.15-0.30 | ILLUSTRATIVE | belum ada |
| confluence / absorption / regime thresholds | varied | ILLUSTRATIVE | belum ada |

## Jalur kalibrasi yang valid (belum selesai)

Backfill v1 dengan `trenches` (token baru) TIDAK valid untuk outcome historis.
Sumber data yang benar:

1. **Token yang sudah MATANG** (bukan baru lahir): universe dari token berumur
   >= 7-30 hari. Sumber: DexScreener token dengan age, atau GMGN tren
   `completed` + filter created_timestamp lama, atau kumpulan token historis.
2. **Definisi outcome berbasis harga + LP/dev (berlabel)**: rug = LP removed /
   dev dump / crash dari peak; survived = tidak rug; pumped = naik sustained.
   Label harus data historis, bukan snapshot 2 hari.
3. **Fitur insider**: label dari `creator_created_count`, `is_honeypot`,
   `fund_from_address` (EV-021), `bundler_trader_amount_rate` di trenches —
   fitur ini ADA di data nyata, tinggal dikumpulkan untuk token berumur cukup.
4. Jalankan `walk_forward` (backtest/walk_forward.py) pada dataset berlabel tsb,
   evaluator metrik sasaran (mis. presisi/recall kelas rugged) sebelum set
   `calibrated=True`.

## Riwayat perubahan

- 2026-08: backfill v1 (GMGN trenches, 20 sampel, semua survived) -> INSIGHT:
  trenches = token baru, tidak valid untuk outcome historis. Belum ada threshold
  yang dinyatakan terkalibrasi. Tool backfill (`backfill.py`,
  `scripts/calibrate.py`) SIAP dipakai untuk universe token matang.
