# Audit Bobot Inti — SFC Memecoin Screening Engine
Tanggal: 2026-08-09 | Sumber: docs folder B (spec v5 §6.15, §8) + repo aktual

## STATUS: Langkah bernilai-tinggi 1-4 SELESAI (2026-08-09)
- GMGN `market_stats` method + `TokenMarketStats` dataclass ditambahkan (fetchers/gmgn.py) — ambil holder_count, wallet_tags_stat (smart/sniper/bundler/fresh/whale/renowned/rat), locked_ratio, buy/sell/volume 24h dari `token info`.
- `_map_core_weights()` (wiring.py) mengisi organic/smart_money/safety dari data nyata, bukan konstanta.
- `_map_alpha_raw()` (wiring.py) memperkaya alpha_raw dengan momentum (price_24h) + buy pressure (buy_volume share) + liquidity — tak lagi hanya volume.
- `build_features` kini memanggil market_stats & mengisi SEMUA bobot inti terukur (alpha/organic/smart_money/safety).
- Live verify (CATE): alpha=100 (vol $15M + mom +4.1%), organic=31.3 (1000 bundler+1000 fresh → tidak organik), smart_money=59.6 (154 smart), safety=50 (locked 0.0002).
- 291 test hijau (+6).

## Tujuan
Menilai apakah bobot inti (Alpha / Organic / Safety / Smart Money) benar-benar
DIUKUR dari data nyata, atau hanya konstanta. Karena Risk-Adjusted Alpha =
Alpha × (1 − downside_penalty), jika Alpha/Organic/Smart Money hardcoded, maka
ranking akhir didorong hampir seluruhnya oleh PENALTI (insider/OKX/sybil),
bukan oleh kualitas yang terukur.

## Status aktual (dibaca dari wiring.build_features)

| Bobot | Rumus saat ini di wiring | Sumber | Dinilai |
|-------|--------------------------|--------|---------|
| alpha_raw | 40 + vol/1M × 40 (cap 100) | DexScreener volume_24h | PROXY mentah |
| organic_raw | **50.0 (HARDCODED)** | — | KONSTANTA |
| safety_raw | 50 + liq/1M × 30 (cap 100) | DexScreener liquidity | PROXY mentah |
| smart_money_raw | **50.0 (HARDCODED)** | — | KONSTANTA |

Akibat: organic & smart_money = 50 untuk SEMUA token → tidak membedakan apa pun.
alpha/safety hanya fungsi linier volume/liquidity → sangat korelasi dengan ukuran
token (token besar selalu "lebih baik" walau bisa jadi lebih buruk secara risiko).

## Data nyata yang SUDAH tersedia untuk mengisi bobot (terverifikasi di repo)

### 1. TokenMarketInfo (DexScreener, sudah di-fetch)
- volume_24h, liquidity_usd, mcap/fdv, holders, price_usd
- → sudah dipakai alpha/safety

### 2. GMGN trending / token market (data ADA di GMGN API — dibuktikan field-nya
di backfill.py baris 188-197), TAPI BELUM ada fetcher method + BELUM di-fetch
oleh wiring:
- holder_count
- bundler_rate
- sniper_count
- top70_sniper_hold_rate
- dev_team_hold_rate
- creator_close
- rug_ratio
- entrapment_ratio
- renounced_mint
- twitter_create_token_count
- is_honeypot

### 3. WalletAnalytics (GMGN wallet_stats — sudah di-fetch, TAPI hanya untuk DEV
wallet, belum untuk bobot agregat token)
- win_rate, early_entry_rate, social_influence, suspected_insider_hold_rate,
  fresh_wallet_rate, bundler_trader_amount_rate, rat_trader_amount_rate

### 4. OKX insider signals (sudah di-fetch)
- rugPullCount, devHoldingsPercent, snipers/insiders/bundlers/top10 composition

## Pemetaan yang benar (bobot → data yang sudah ada)

| Bobot | Seharusnya diisi dari | Alasan (spec v5) |
|-------|----------------------|------------------|
| organic_raw | holder_count, top70_sniper_hold_rate (invers), dev_team_hold_rate (invers), creator_close (invers), rug_ratio (invers), entrapment_ratio (invers), social_attention | Quality of demand (spec §8: Organic = kualitas demand). Holder count tinggi + konsentrasi sniper/dev rendah = demand organik |
| smart_money_raw | win_rate, early_entry_rate, social_influence (dari wallet_stats), suspected_insider_hold_rate (invers), bundler_trader_amount_rate (invers) | Quality of wallet flow (spec §8). Smart money = wallet berpola profitable/early, bukan bundler/sniper |
| safety_raw | liquidity, lp_locked_pct, renounced, sell_sellable, is_honeypot, rug_ratio | Structural safety (sudah sebagian; perlu tambah LP/renounce yang sudah di-capture) |
| alpha_raw | volume, price momentum, mcap, liquidity, social_attention | Raw opportunity (volume+liquidity+momentum) |

## Gap kritis (akar masalah sebenarnya)

1. **Fetcher GMGN tidak punya method market stats token** — data holder/sniper/
   bundler/dev_team_hold_rate ADA di GMGN tapi tidak pernah di-fetch. Ini blokir
   utama untuk mengisi organic & smart_money dengan benar.
2. `organic_raw` & `smart_money_raw` = 50 konstanta → perlu GMGN market method +
   pemetaan formula.
3. `wallet_stats` hanya di-fetch untuk DEV wallet, bukan untuk agregat pembeli
   token → smart_money tidak terwakili dengan baik.

## Kesimpulan (analisis, bukan action)

- Engine yang belum dikerjakan (Microstructure/PE/LS) BUKAN akar masalah — data
  microstructure sebagian sudah ada (dex_flow EV-001) dan tidak akan bernilai
  selama bobot inti konstanta.
- Prioritas bernilai TINGGI: (a) tambah fetcher method `gmgn.market_stats` untuk
  ambil holder/sniper/bundler/dev_team_hold_rate, (b) isi organic & smart_money
  dari data itu, (c) perkaya safety dari LP/renounce yang sudah di-capture.
- Ini akan membuat Risk-Adjusted Alpha mulai membedakan kualitas positif, bukan
  hanya "paling tidak buruk".

## Rekomendasi (nilai vs usaha)
| Item | Nilai | Usaha | Putuskan |
|------|-------|-------|----------|
| GMGN market_stats method + fetch | TINGGI | Sedang | ✅ |
| Isi organic_raw dari holder/sniper/dev_team_hold_rate | TINGGI | Rendah (setelah method ada) | ✅ |
| Isi smart_money_raw dari wallet_stats dev | SEDANG | Rendah | ✅ (partial) |
| Perkaya safety_raw dari LP/renounce | SEDANG | Rendah | ✅ |
| Microstructure/PE/LS engine baru | RENDAH | Tinggi | ⏸ Tunda (redundant dgn dex_flow, tanpa kalibrasi) |
| ML ranking (XGBoost) | TERGANTUNG kalibrasi | Tinggi | ⏸ Tunda (doktrin) |
