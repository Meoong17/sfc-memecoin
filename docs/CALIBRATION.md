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

### Label insider sejati — OKX Onchain OS (data/insider_labeled_dataset_okx_v1.json)

Sumber kedua (TERPISAH dari GMGN) untuk memperkaya kelas minority rug/dev_dump
yang GMGN trending tidak bisa hasilkan (n=120 GMGN: 0 rug). Modul
`fetchers/okx.py` (shell ke `onchainos memepump` CLI, auth 3 kredensial) +
`classify_okx_outcome`/`label_from_okx` di `backtest/insider_labels.py`.

- Field OKX PERSEN (0-100), beda dari fraksi GMGN. Sinyal:
  `tags.{devHoldingsPercent,insidersPercent,snipersPercent,bundlersPercent,
  top10HoldingsPercent}`, `devLaunchedInfo.{rugPullCount,totalTokens}`,
  `devHoldingInfo.devHoldingPercent`.
- `scripts/label_insiders.py --universe okx` (blend NEW/MIGRATING/MIGRATED).
- Live collect (n=8, smoke): **6 clean / 1 rug / 1 dev_dump**. PENTING: OKX
  menghasilkan label `rug` pertama (GMGN trending selalu 0 rug). Contoh nyata:
  - RUG: `rugPullCount=69`, `totalTokens=14.594` (serial rugger kentara),
    `devHoldingPercent=0`.
  - DEV_DUMP: `devHoldingPercent=0` (dev jual habis), `snipersPercent=50.6%`,
    `top10HoldingsPercent=50.5%`.
- Quota OKX longgar (basicFreeQuota=1.000.000) -> jalur aktif yang bagus saat
  GMGN kena rate-limit ban (~8 jam).
- Threshold OKX (OKX_RUG_ANY=1, OKX_DEV_DUMP_HOLDING=20%, OKX_DEV_DUMP_COORD=30%,
  OKX_EARLY_SELL_TOP10=50%, OKX_EARLY_SELL_COORD=20%) TETAP ILLUSTRATIVE —
  n=8 terlalu kecil utk walk-forward. Langkah berikut: perluas dataset OKX
  (limit 30-50) lalu `walk_forward_insider.py` utk verdict stabilitas kelas
  rug/dev_dump. 249 test hijau.

### Label insider sejati — OKX v2 (data/insider_labeled_dataset_okx_v2.json)

Perluas ke n=40 (blend NEW/MIGRATING/MIGRATED). **Variasi kelas nyata:
29 clean / 6 rug / 4 early_sell / 1 dev_dump.** OKX memberi 6 label `rug`
(GMGN trending n=120: 0 rug) — konfirmasi OKX menyelesaikan gap kelas minority.

- **BUG FIX (penting): `created_ts` OKX awalnya MILLISECONDS (13 digit) —
  `walk_forward_insider.py` memakai `datetime.fromtimestamp` (DETIK).** Tanpa
  normalisasi, fold temporal akan salah (tahun ~57000). `_okx_universe` kini
  mengubah ms->detik (bagi 1000 bila > 1e12). Dataset v1 juga diregenerasi.
  GMGN v2_large sudah detik (10 digit), tidak terpengaruh.
- Walk-forward (dirty-rate = rug+dev_dump, urut created_ts, min_train 20):
  **mean 0.400 -> INSUFFICIENT** (hanya 2 fold: 0.100 / 0.700). n=40 + kelas
  minoritas (6 rug/1 dev_dump) masih terlalu kecil & tidak stabil temporal.
  Verdict jujur sesuai doktrin: **threshold OKX TETAP ILLUSTRATIVE.**
- Tempel: span created_ts ~23.5 jam (29 distinct) — universe OKX mememump
  didominasi token baru-baru dibuat, jadi fold temporal terbatas. Untuk
  stabilitas rug yang andal butuh n>100 + sebaran waktu lebih panjang.

### OKX dev-reputation sebagai fitur insider langsung (wiring scoring)

Selain label, OKX dev-reputation kini di-wire ke JALUR SCORING live sebagai
evidence insider langsung (independen dari funding-cluster EV-021):

- `TokenFeatures.okx_signals` + `InsiderInputs.okx_signals` (pipeline.py).
- `InsiderIntelligenceEngine.analyze`: membaca `okx_rug_pull_count` /
  `okx_dev_holding_percent` / `okx_dev_total_tokens` / komposisi holder dan
  menambah evidence + probabilitas (ILLUSTRATIVE): serial-rugger 0.30,
  dev-sold-off 0.20, coordinated (snipers/insiders/bundlers>=30%) 0.15,
  top10>=60% 0.10. Kontribusi ini BUKAN menggantikan funding-cluster, tapi
  menambah (skor cap 1.0).
- `wiring.build_features`: saat okx tersedia & chain solana, fetch
  `okx.insider_signals(addr)` -> `f.okx_signals`. Degradasi aman (gagal/empty/
  non-sol -> okx_signals={}).
- **CATATAN jujur:** `insider_signals` hanya berisi field dev-reputation
  (rugPullCount/devHoldingsPercent/devTotalTokens) — komposisi holder
  (snipers/insiders/bundlers/top10) hanya tersedia saat koleksi universe via
  list `tokens`, bukan per-token di jalur scoring. Sinyal terkuat (serial
  rugger + dev sold-off) tetap aktif.
- Verifikasi live (`collect_live --limit 4`): insider_probability kini
  bervariasi 0.20-0.70 (baseline funding-cluster 0.20). Probe langsung:
  token devhold=0/total=1 -> insider_prob 0.20 dari evidence okx_dev_sold_off.
- Kontribusi probabilitas ILLUSTRATIVE (belum walk-forward) — konsisten doktrin:
  menambah SINYAL nyata, bukan mengklaim terkalibrasi. 259 test hijau.

### OKX holder-composition tags per-address (token-details) — wiring

Perbaiki gap sebelumnya: `insider_signals` (token-dev-info) hanya membawa field
dev-reputation, komposisi holder tidak masuk scoring per-token. Kini:

- `fetchers/okx.py`: `token_tags_by_address(addr)` — memanggil `memepump
  token-details --address <addr>` (mengembalikan `tags` yang SAMA dengan list
  endpoint: bundlers/insiders/snipers/freshWallets/suspectedPhishing/top10
  percent + totalHolders). Degradasi aman: `data:null` (bukan token mememump)
  atau gagal -> {}.
- `wiring.build_features`: `okx_sig.update(token_tags_by_address(addr))` —
  merge komposisi holder ke `okx_signals` sehingga engine melihat SET sinyal
  OKX lengkap per token.
- Verifikasi live (collect_live --limit 3): tanpa warning (merge mulus), insider
  0.20-0.40. Probe end-to-end: token TOAD (top10 98.3%, snipers 98.2%) ->
  insider_prob 0.45, evidence `okx_coordinated_98.2%` + `okx_concentrated_top10_
  98.3%` + `okx_dev_sold_off_0.0%`. Semua 14 key OKX ter-merge.
- 263 test hijau (+4: token_tags_by_address parses/null/fail, wiring merge).

### FIX GAP: OKX evidence kini benar-benar menurunkan RAA (efek rantai)

Audit objektif menemukan GAP: `insider_probability` dinaikkan OKX (0→0.75) TAPI
`Risk-Adjusted Alpha` TIDAK berubah (60→60) karena `AlphaRiskEngine` hanya
mengonsumsi `exit_liquidity_risk`/`ihr_class`/`insider_distribution` — BUKAN
`insider_probability`. Semua wiring OKX ke scoring tadinya DEKORATIF (tidak
mengubah ranking Telegram). DIPERBAIKI tanpa double-count:

- `InsiderResult.dev_reputation_risk` (LOW/MED/HIGH) — downside OKX terpisah
  dari IHR/exit. Set di `insider_intel.analyze`: HIGH jika serial rugger
  (rugPullCount>=1); MED jika dev sold-off ATAU koordinasi (snipers/insiders/
  bundlers>=30%). LOW jika tidak ada sinyal OKX.
- `AlphaRiskEngine`: `_DEV_REP_PENALTY = {LOW:0, MED:0.15, HIGH:0.30}` +
  downside factor `okx_dev_reputation_{level}`.
- Verifikasi deterministik: OKX serial rugger (rug=5, top10=98%) -> insider_prob
  0.75, dev_reputation_risk=HIGH, **RAA 60 -> 42**. Efek rantai tertutup.
- Tetap ILLUSTRATIVE (belum walk-forward). 269 test hijau (+6: dev_reputation
  level di insider_intel, penalty HIGH/MED/LOW di alpha_risk).

### Verifikasi live end-to-end (DevRisk di ranking + Telegram)

- `TokenScore.summary()` kini mengekspos `dev_reputation_risk` (dibaca dari
  `outputs.insider`), sehingga field itu tampil di snapshot/ranking.
- Format Telegram menambahkan `DevRisk={LOW/MED/HIGH}` per token + definisi di
  legenda. `scripts/telegram_notify.py` diberi sys.path bootstrap agar bisa
  dijalankan langsung (sebelumnya `ModuleNotFoundError: config`).
- Verifikasi live (`collect_live --limit 6`, snapshot /tmp/snap_live.json):
  | RAA | insider | DevRisk | sym  |
  |----|---------|---------|------|
  | 41.4 | 0.00 | LOW  | FEATHY (tertinggi) |
  | 36.4 | 0.40 | MED  | SOOK  |
  | 35.5 | 0.20 | MED  | Oggie |
  | 35.4 | 0.20 | MED  | BITPEPE |
  | 34.1 | 0.40 | MED  | IPO   |
  | 28.6 | 0.50 | HIGH | FRENS (terendah) |
  RAA kini bervariasi 28.6-41.4 (bukan rata ~40), DevRisk HIGH (FRENS) -> RAA
  terendah, DevRisk LOW (FEATHY) -> RAA tertinggi. Efek rantai OKX ->
  insider_probability -> dev_reputation_risk -> RAA -> ranking terbukti di data
  nyata. `telegram_notify.py /tmp/snap_live.json` -> sent=True (pesan terkirim).

### Contract status badge (smart-contract coin tampil jelas di Telegram)

Permintaan user: token dengan kontrak aman/terverifikasi harus tampil jelas.

- `TokenFeatures`: +4 field keamanan kontrak (contract_sell_sellable,
  contract_lp_locked_pct, contract_lp_burned, contract_renounced), di-capture
  dari ContractFacts GMGN di `wiring.build_features`.
- `TokenScore.contract_status` (VERIFIED/LOCKED/RISKY/CRITICAL/UNKNOWN) + helper
  `_contract_status()` di pipeline:
  - 🛡️ VERIFIED = aman & terverifikasi: bukan honeypot + sellable + renounced +
    LP locked/burned (secure >= 50%) — badge coin aman.
  - 🔒 LOCKED = LP aman tapi belum renounced.
  - ⚠️ RISKY = LP tidak terjamin.
  - 🚨 CRITICAL = honeypot / tidak bisa jual.
  - ❔ UNKNOWN = tidak ada fakta GMGN (degradasi).
- `_gmgn_renounced_from_notes` parsing robust (bool True repr / string "True").
- Format Telegram: `Contract: 🛡️ VERIFIED` per token + legenda 4 level.
  `_fmt_usd` diperbaiki (cap $100k+ -> $100,000, bukan 4 desimal).
- Verifikasi live (collect_live --limit 6): Aether/AURIS = VERIFIED (renounced +
  LP aman) -> RAA 40.6/40.4 (tertinggi); FRENS = LOCKED + DevRisk HIGH ->
  RAA 29.2 (terendah). `telegram_notify.py /tmp/snap_contract.json` ->
  sent=True. 277 test hijau (+8).

### Telegram format — harga/mcap + legenda Konfluensi lengkap (revisi)

Format pesan ranking diperbaiki: (1) tiap token kini menampilkan symbol, harga
(sub-cent diformat pintar $0.00000120), market cap (suffix M/B/T $2.50M), label
Konfluensi, dan alamat token; (2) legenda "Cara baca skor" Konfluensi diperbaiki
— sebelumnya hanya menulis MODERATE_OPPORTUNITY, sekarang menjelaskan keempat
label nyata dari engines/confluence.py: HIGH_CONFLUENCE / MODERATE_OPPORTUNITY /
NEUTRAL / FALSE_MOMENTUM. Data harga/mcap ditangkap di `collect_live.py` via
`enrich_market` lalu ditempel ke snapshot (`_attach_market`) sebelum dikirim.
Plain text (tanpa markdown) agar render bersih.

### Telegram notifier (scripts/telegram_notify.py + collect_live --notify)

Bot @SfcMeme_bot (TELEGRAM_BOT_TOKEN/CHAT_ID di .env) push ranking screener
ke DM meong via Bot API. Verifikasi live: SENT=True. `collect_live --notify`
mengirim ranking setelah scoring. Load .env via config.settings (jalan dari
shell kosong). 5 test.

### Wiring GMGN wallet_stats -> classification features (live)

Gap terakhir di live path di-tutup: `wiring.build_features` kini memanggil
`gmgn.wallet_stats(dev_wallet)` dan mengisi `TokenFeatures.wallet_analytics`.
Pipeline wallet_classify memakai sinyal tersebut (win rate, fresh-wallet,
early-entry) alih-alih empty-signal. Verifikasi live: `wallet_analytics=1`
per token dengan dev wallet. 2 test baru.

### Cron + Telegram format

- Cron `collect_live --notify` tiap 6 jam (script `~/.hermes/scripts/sfc_memecoin_collect.sh`
  -> push ranking ke Telegram via Bot API, independen dari Hermes delivery).
- Format pesan Telegram diperjelas: header + emoji stats (Universe/Admitted/
  Blocked), per-token `RAA | Conf | Insider %`, legenda "Cara baca skor"
  mendefinisikan RAA/Insider/Conf/Konfluensi dalam Bahasa Indonesia, disclaimer
  ILLUSTRATIVE. Plain text (tanpa markdown) agar render bersih.

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
