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

### Hasil backfill nyata — v3 (data/labeled_dataset_v3_variety.json)

Pelajaran dari v2: universe trending 24h tunggal -> semua rugged (bias sampel).
Solusi: gabungkan trending multi-interval (1h/6h/24h) + label berbasis harga
FINAL (`final_return_pct`) bukan max_drawdown-only (yang over-label pump-then-
crash sebagai rugged walau final > launch).

- Universe: gabungan trending 1h+6h+24h, min-created 7d (156-157 token unik).
- 40 sampel dilabeli. **VARIASI OUTCOME NYATA: 24 pumped, 8 survived, 8 rugged.**
- Walk-forward mean score **0.279 -> INSUFFICIENT** (rug rate antar fold
  berfluktuasi 0.05-0.49). Ini verdict VALID (data beragam, evaluator menguji
  stabilitas) -> **threshold tetap ILLUSTRATIVE.**

Korelasi fitur insider vs final_return (n=40, BERAGAM — lebih valid dari v2):

| Fitur | corr(final) | rugged avg | pumped avg | survived avg | Baca |
|---|---|---|---|---|---|
| twitter_create_token_count | **+0.921** | 7.0 | 207.8 | 172.3 | aktivitas penciptaan X tinggi -> PUMPED (bukan rug) |
| entrapment_ratio | +0.443 | 0.141 | 0.291 | 0.213 | entrapment tinggi -> final lebih tinggi |
| bundler_rate | +0.249 | 0.130 | 0.155 | 0.103 | lemah-positif |
| rug_ratio | -0.115 | 0.416 | 0.349 | 0.507 | lemah |
| sniper_count | -0.048 | 27.1 | 22.4 | 20.9 | lemah |
| top70_sniper_hold_rate | -0.079 | 0.009 | 0.015 | 0.010 | lemah |
| dev_team_hold_rate | -0.099 | 0.009 | 0.007 | 0.010 | lemah |

Temuan konsisten lintas dataset (v2 & v3): `twitter_create_token_count`
berkorelasi kuat-positif dengan outcome menguntungkan (pumped/survived).
Hipotesis: token dengan jejak sosial X aktif cenderung bertahan/pump; token
mati (rugged) punya jejak sosial ~0. Ini KANDIDAT fitur untuk kalibrasi insider,
perlu verifikasi kausalitas + n lebih besar sebelum jadi threshold.

### Kenapa belum bisa kalibrasi (final)

| Masalah | Dampak |
|---|---|
| n=40 beragam tapi masih moderat | walk-forward INSUFFICIENT (0.279) -> threshold tetap ILLUSTRATIVE |
| Korelasi kuat (twitter_create_token_count) belum = kausal | butuh verifikasi + dataset label insider sejati (rug/dev-dump/early-sell) |
| Threshold IHR/ITA butuh label insider per-wallet | label = rug/dev-dump/early-sell, butuh data historis panjang + korelasi label |
| Universe trending bias | populasi meme coin yang beragam membutuhkan sumber tambahan (dex, trenches, historical) |

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
