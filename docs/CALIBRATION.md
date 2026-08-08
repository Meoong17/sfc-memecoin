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

### Hasil backfill nyata — v4 (data/labeled_dataset_v4_large.json)

Pelajaran dari v3: n=40 masih moderat; temuan twitter_create_token_count +0.921
butuh uji stabilitas di n lebih besar. Solusi: perluas trending multi-interval
(1h/6h/24h/7d) + max_tokens 140, min-age 2d, max-age 120d.

- Universe: trending 1h+6h+24h+7d, min-created 7d.
- **122 sampel dilabeli. VARIASI OK: 55 pumped, 29 rugged, 38 survived.**
- Walk-forward (di dataset tersimpan, bukan re-fetch) mean score **0.623 ->
  SUPPORTED** (fold rug-rate 0.000-0.891; perhatikan fold 2 = 0.000 dan fold 10 =
  0.200 — mean ditarik naik oleh fold akhir yang kebetulan konsisten; evaluator
  rug-rate-stability lemah, TIDAK menguji kekuatan prediktif). Verdict tetap
  **hati-hati**: ini stabilitas label, bukan bukti threshold.

Analisis fitur insider vs final_return (n=122, temporal-sorted):

| Fitur | Pearson | Spearman | rugged avg | pumped avg | survived avg | Baca |
|---|---|---|---|---|---|---|
| twitter_create_token_count | **+0.898** | **+0.039** | 11.9 | 104.0 | 84.2 | Pearson tinggi TAPI rank ~0 |
| holder_count | +0.780 | — | 2749 | 7643 | 2702 | likuiditas/ketenaran, bukan insider |
| entrapment_ratio | +0.279 | — | 0.21 | 0.24 | 0.22 | menurun drastis vs v3 (0.443) -> tidak stabil |
| bundler_rate | +0.215 | — | 0.08 | 0.11 | 0.11 | lemah |
| rug_ratio | -0.067 | — | 0.29 | 0.31 | 0.27 | lemah |
| sniper_count | +0.010 | — | 24.8 | 19.7 | 18.4 | ~0 |
| top70_sniper_hold_rate | -0.049 | — | 0.02 | 0.01 | 0.03 | lemah |
| dev_team_hold_rate | -0.046 | — | 0.02 | 0.01 | 0.02 | lemah |

**TEMUAN METODOLOGIS PENTING (v4 menolak temuan v3):**
`twitter_create_token_count` Pearson = +0.898 TAMPAK kuat, TAPI:
1. **Spearman (rank-robust) = +0.039** — korelasi Pearson didorong outlier
   ekstrem (beberapa token dengan count ribuan + return ribuan %), bukan
   hubungan monotonik sebenarnya. Rank-correlation ~0.
2. **Temporal chunking (urut launch): [+0.98, -0.08, -0.01, -0.14, -0.20]** —
   korelasi hanya muncul di subset terawal, runtuh di SEMUA chunk berikutnya.
3. **Bootstrap CI [-0.084, +0.980] termasuk 0** -> tidak signifikan statistik.

KESIMPULAN JUJUR: temuan v3 (twitter_create_token_count +0.921) TIDAK
mereplikasi secara temporal/robust. Nilai Pearson tinggi itu artefak outlier.
**BUKAN fitur insider yang stabil — JANGAN jadikan threshold.** Ini persis pola
doktrin: narasi -> uji empiris (n>100, rank-robust, temporal) -> tidak stabil ->
jangan build. Semua threshold tetap ILLUSTRATIVE.

### Label insider sejati — on-chain (data/insider_labeled_dataset_v1.json)

Setelah v4 membuktikan label proxy harga (twitter_create_token_count) rapuh,
kita bangun label INSIDER SEJATI berbasis perilaku on-chain dev/holder/LP — bukan
harga. Modul `backtest/insider_labels.py` (rug / dev_dump / early_sell / clean).

- Sumber (GMGN live, terverifikasi): `token traders --tag dev` (dev sell ratio,
  sell/buy tx count, transfer-out) + `token security` (top_10_holder_rate,
  is_honeypot, lock_summary, renounced).
- Live collect `scripts/label_insiders.py` -> **19 sampel: 14 clean, 4 dev_dump,
  1 early_sell**. Variasi kelas nyata, semua dari data on-chain sejati.
- **TEMUAN METODOLOGIS: `lock_summary.lock_percent="0"` BUKAN berarti LP tak
  terkunci.** `lock_detail[].is_blackhole=true` + `burn_ratio=1` = LP DIBAKAR
  permanen ke dead address (aman, tak bisa ditarik). Interpretasi awal (rug saat
  lock_percent<30%) salah; diperbaiki: LP burned/locked = SECURE, dev dump pada
  LP secure = dev_dump (bukan rug). Rug = honeypot ATAU dev dump + LP tak secure.

Status: label sejati KONFIRMASI bisa dikumpulkan dari data on-chain nyata, tapi
n=19 masih kecil. Threshold insider (DEV_DUMP_SELL_RATIO=0.6, EARLY_SELL_TOP10=0.3,
dst) tetap ILLUSTRATIVE — butuh dataset lebih besar + walk-forward sblm enforce.

### Label insider sejati — v2 (data/insider_labeled_dataset_v2_large.json)

Perluas ke n>100 via universe GMGN `trending` (DexScreener profiles cap ~30).
120 sampel live, masing2 dengan `created_ts` (untuk temporal walk-forward).
Distribusi: 71 clean / 45 dev_dump / 4 early_sell.

Walk-forward (dirty-rate = dev_dump+rug, urut created_ts, min_train 20):
mean **0.531 -> INSUFFICIENT** (fold 0.143-0.918). Label insider on-chain JUGA
belum stabil secara temporal di n=120 -> threshold insider TETAP ILLUSTRATIVE.
Catatan: early_sell hanya 4 sampel, rug 0 (universe trending = LP dibakar aman);
kelas minority belum cukup untuk menilai. Ini verdict jujur sesuai doktrin.

### Telegram notifier (scripts/telegram_notify.py + collect_live --notify)

Bot @SfcMeme_bot (TELEGRAM_BOT_TOKEN/CHAT_ID di .env) push ranking screener
ke DM meong via Bot API. Verifikasi live: SENT=True. `collect_live --notify`
mengirim ranking setelah scoring. Load .env via config.settings (jalan dari
shell kosong). 5 test.

### Wiring EV-021 funding trace ke pipeline score (live)

`wiring.build_features` kini mengisi `funding_clusters` (EV-021) dari Helius:
GMGN dev wallet -> `helius.fetch_funding_edges` -> FundingEdge list -> pipeline.

- Verifikasi live: token dengan funding cluster nyata (2-15 edges) kini
  `insider_probability` = **0.200** (sebelumnya selalu 0.00 di live score).
- Hanya Solana (Helius = RPC Solana); non-sol & kegagalan RPC terdegradasi aman.
- Fix env: HELIUS_API_KEY punya trailing space di .env -> HTTP 401; di-strip.

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
