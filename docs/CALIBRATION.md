# CALIBRATION — Live Ledger

Doktrin: **tidak ada threshold/formula produksi tanpa walk-forward re-validation
pada outcome historis berlabel** (rugged / survived / pumped). Setiap perubahan
threshold dicatat di sini dengan bukti empiris.

## Status: SEMUA threshold masih ILLUSTRATIVE (calibrated=False)

Backfill v1 & v2 (2026-08) DIJALANKAN dengan data nyata GMGN. Hasil jujur:
**data masih belum cukup untuk kalibrasi.** Threshold tetap ILLUSTRATIVE dan
TIDAK ditegakkan di produksi oleh `VetoEvaluator`.

### Hasil backfill nyata — v1 (data/labeled_dataset_v1.json)

- Universe: 160 token dari GMGN `market trenches` (solana).
- Hanya 3 token berusia >= 2 hari; maksimal 2 hari. Trenches = token BARU lahir.
- 20 sampel dilabeli (min-age 0). Semua `survived`, semua `dd=0%`.
- Walk-forward "mean score 1.000" = **ARTEFAK DATA HOMOGEN, BUKAN validasi.**
  Karena semua label identik, rugged-rate train==test==0 jadi "konsisten".
  Ini TIDAK membuktikan threshold apa pun.

### Hasil backfill nyata — v2 (data/labeled_dataset_v2_mature.json)

Pelajaran dari v1: trenches tidak memberi horizon historis. Solusi: universe
MATANG dari `market trending --min-created 7d` + kline 1d dari LAUNCH
(`--from created_timestamp`). Terverifikasi live: token age 720 hari, kline 100 bars.

- Universe: 79 token matang (solana, trending 24h, min-created 7d).
- 15 sampel dilabeli. **Semua `rugged`** (peak 238%-261.473%, dd -35% s/d -98%).
- Walk-forward score 1.000 lagi-lagi **ARTEFAK DATA HOMOGEN** (semua rugged ->
  train==test rugged-rate==1.0), bukan bukti threshold.

Analisis korelasi fitur insider vs severity (n=15, semua rugged — sampel kecil &
tanpa variasi outcome, JADI HIPOTESIS awal, bukan kalibrasi):

| Fitur | corr(peak) | corr(dd) | Baca |
|---|---|---|---|
| twitter_create_token_count | **+0.818** | -0.024 | serial creator -> pump tinggi (pola dev/insider) |
| top70_sniper_hold_rate | -0.194 | **+0.419** | sniper hold tinggi -> rug dangkal |
| dev_team_hold_rate | -0.188 | **+0.390** | dev hold tinggi -> rug dangkal |
| bundler_rate | +0.085 | -0.255 | lemah |
| rug_ratio | -0.237 | -0.164 | lemah |
| sniper_count | +0.040 | -0.031 | lemah |

Catatan: field insider tersedia DI data trending nyata (`bundler_rate`,
`sniper_count`, `top70_sniper_hold_rate`, `dev_team_hold_rate`, `rug_ratio`,
`entrapment_ratio`, `twitter_create_token_count`), bukan hanya di trenches.
Ini menyediakan fitur untuk kalibrasi IHR/insider pada universe yang cukup.

### Kenapa belum bisa kalibrasi (final)

| Masalah | Dampak |
|---|---|
| n kecil + semua label homogen (v1 survived, v2 rugged) | walk-forward score 1.000 = artefak, tak ada variasi untuk ukur diskriminasi |
| Universe tunggal (trenches / trending 24h) bias sampel | bukan populasi meme coin yang beragam |
| Threshold IHR/ITA butuh label insider | label insider = rug/dev-dump/early-sell, butuh data historis panjang + korelasi label |
| Korelasi fitur v2 dari n=15 | sinyal awal, butuh n>=50-100 beragam utk threshold produksi |

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
