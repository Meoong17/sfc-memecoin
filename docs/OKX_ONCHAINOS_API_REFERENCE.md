# OKX Onchain OS DEX/Market API — Referensi (Verified 2026-08-08)

Status: **VERIFIED terhadap dokumen resmi + source code SDK/skills OKX.** Bukan
tebakan. Belum ada kredensial OKX di `.env` → integrasi TIDAK dimulai; dokumen ini
adalah peta sebelum ngoding (sesuai keputusan).

## Klaim user vs fakta terverifikasi

| Klaim | Verifikasi | Hasil |
|---|---|---|
| OKX Onchain OS sediakan DEX API + Market API | `web3.okx.com/onchainos/dev-docs` | ✅ Benar. Ada **Trade API** (swap/aggregator) + **Market API** (price/token/balance/tx) |
| Dukung Solana + EVM | docs + SDK | ✅ Solana, Ethereum, Base, BSC, Arbitrum, Polygon, XLayer, 20+ chain |
| Agregasi 500+ DEX / 20+ chain | klaim OKX | ⚠️ Tidak bisa diverifikasi angka pastinya dari kode; docs klaim "hundreds of DEX". Angka "500+/20+" dari user/README, jangan dibawa sebagai fakta |

## Dua jalur akses (penting — menentukan cara integrasi)

1. **Open API (REST, key-based)** — butuh Project ID + API key + secret + passphrase
   dari OKX Developer Portal. Auth = HMAC-SHA256, header `OK-ACCESS-*`. Cocok utk
   integrasi server-side (fetcher), mirip model GMGN API key.
2. **Onchain OS CLI/skills** (`npx skills add okx/onchainos-skills`) — CLI Rust
   (`onchainos`) + skills siap pakai. Bisa autentikasi via env vars. Pola ini PERSIS
   seperti `gmgn-cli` yang sudah kita pakai di `fetchers/gmgn.py`.

## Auth (Open API) — verified dari SDK `okx/dex-api-library` `lib/shared.ts`

String yang ditandatangani:
```
stringToSign = timestamp + method + requestPath + queryString
sign = base64( HMAC_SHA256(stringToSign, secretKey) )
```
Header:
```
OK-ACCESS-KEY:      <api key>
OK-ACCESS-SIGN:     <sign di atas>
OK-ACCESS-TIMESTAMP:<ISO8601, harus sama dgn yg di-sign>
OK-ACCESS-PASSPHRASE:<passphrase>
OK-ACCESS-PROJECT:  <project id>
```
Env yang dibutuhkan (dari README SDK): `OKX_PROJECT_ID`, `OKX_API_KEY`,
`OKX_SECRET_KEY`, `OKX_API_PASSPHRASE`. (CLI skills pakai `OKX_API_KEY`/
`OKX_SECRET_KEY`/`OKX_PASSPHRASE`.)

## Endpoint yang relevan untuk SFC Memecoin

### Trade API (verified dari `dex-api-library` + docs)
```
GET /api/v6/dex/aggregator/all-tokens?chainIndex=<idx>   # daftar token (major saja)
GET /api/v6/dex/aggregator/supported/chain               # chain index (Solana=501, ETH=1)
GET /api/v6/dex/aggregator/get-liquidity
GET /api/v6/dex/aggregator/quote
GET /api/v6/dex/aggregator/swap
```
Catatan: `all-tokens` hanya token "major/significant" — TIDAK berguna utk universe
meme coin baru. Bukan pengganti DexScreener/GMGN utk discovery token baru.

### Market API — Token API (verified dari docs v5 + CLI skills)
- `GET /api/v6/dex/market/token/toplist` — **ranking/hot token list** (sumber
  universe alternatif; bisa beri token non-major).
- Token search / metadata / holder statistics / cluster analysis / top traders.
- **Fields insider yang kaya (verified dari `trenches-cli-reference.md`):**
  - `tags.top10HoldingsPercent`, `tags.devHoldingsPercent`, `tags.insidersPercent`,
    `tags.bundlersPercent`, `tags.snipersPercent`, `tags.freshWalletsPercent`,
    `tags.suspectedPhishingWalletPercent`, `tags.totalHolders`
  - `devLaunchedInfo.rugPullCount` / `migratedCount` / `goldenGemCount`
  - `devHoldingInfo.devHoldingPercent` / `devAddress` / `fundingAddress`
  - Bundle/sniper: `totalBundlers`, `bundledValueNative`, `bundlerAthPercent`

### Market API — Trenches / meme (verified dari `okx-dex-market` skill)
`onchainos memepump` commands (READ-ONLY research):
```
memepump chains
memepump tokens --chain <chain> [--stage NEW|MIGRATING|MIGRATED]
memepump token-details --address <addr>
memepump token-dev-info --address <addr>      # dev reputation + rugPullCount
memepump token-bundle-info --address <addr>   # bundle/sniper analysis
memepump similar-tokens --address <addr>      # same-creator tokens
memepump aped-wallet --address <addr>         # co-investor wallets
```
Ini adalah API TERPISAH dari GMGN — potensi bypass rate-limit GMGN yang baru saja
kena ban, DAN menyediakan sinyal insider/dev-rug on-chain yang lebih langsung
(`rugPullCount`, `devHoldingPercent`, `insidersPercent`).

### Market Price API — candlestick/OHLC
- Price / K-line (OHLC) / index price — mirip kebutuhan `KlineAnalyzer` di backfill.
- Endpoint market-price bisa dipakai utk backfill price history (redundan GMGN kline).

## Rate limit & quota (VERIFIED sebagian — batas angka eksplisit TIDAK dipublikasikan)

- CLI skills memakai sistem **quota**: ada "Free Tier" + "Premium", overage berbayar
  via **OKX Agent Payments Protocol (x402)**. Konsep: `{premiumFreeQuota}` gratis,
  kelebihan dihitung per-call (Basic/premium pricing).
- Ada handling HTTP **429** + "rate limit" / "too many" di CLI (verified grep di
  source). Pesan `RATE_LIMIT_BANNED` tidak tampak; OKX memakai model quota/payment,
  bukan IP-ban seperti GMGN.
- ⚠️ Angka persis (mis. "X calls/min", "Y gratis") TIDAK bisa diverifikasi dari kode
  publik — butuh akun developer + cek portal. JANGAN klaim angka yang tak terverifikasi.

## Status integrasi (jujur)

- **Belum ada kredensial OKX** di `/home/ubuntu/sfc_memecoin/.env` (grep `OKX` kosong).
- **`onchainos` CLI belum terinstal** di host.
- Karena itu integrasi TIDAK dimulai — dokumen ini fondasi.

## Rekomendasi integrasi (utk sesi berikut, bila disetujui)

Prioritas terbaik = **Trenches/Token API utk memperkaya kelas minority** insider
(dev_dump/rug) — alamat rate-limit GMGN + data on-chain lebih langsung:

1. Dapatkan kredensial OKX (Developer Portal) + tambahkan ke `.env`.
2. Instal CLI: `npx skills add okx/onchainos-skills` (atau hanya binary `onchainos`).
3. Buat `fetchers/okx.py` (pola sama seperti `fetchers/gmgn.py`: shell ke CLI /
   REST + parse JSON → dataclass). Tambah universe source `--universe okx` di
   `scripts/label_insiders.py` memakai `memepump tokens` + `token-dev-info` /
   `token-bundle-info`.
4. Verifikasi live 1 address dulu (seperti pola raw-probe Helius/GMGN).
5. Jangan jadikan threshold apa pun sebelum walk-forward (doktrin kalibrasi).

## Sumber

- Docs resmi: https://web3.okx.com/onchainos/dev-docs
- Market API intro: https://web3.okx.com/onchainos/dev-docs-v5/dex-api/dex-market-api-introduction
- Auth: https://web3.okx.com/onchainos/dev-docs/home/api-access-and-usage
- SDK: https://github.com/okx/dex-api-library  (`lib/shared.ts` = auth HMAC)
- Skills: https://github.com/okx/onchainos-skills (`skills/okx-dex-market/`)
- Get tokens: https://web3.okx.com/onchainos/dev-docs/trade/dex-get-tokens
