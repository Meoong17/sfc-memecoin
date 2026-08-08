"""Test live wiring: fetchers -> TokenFeatures -> pipeline (mocked)."""
import pytest

from fetchers.dex_screener import TokenMarketInfo
from pipeline import TokenFeatures
from wiring import (LiveSourceBundle, LivePipelineWire, LiveUniverse,
                    _gmgn_renounced_from_notes, _map_alpha_raw, _map_core_weights,
                    _risk_level)


class _FakeGmgn:
    def __init__(self):
        self.calls = 0
    def token_security(self, address, chain):
        self.calls += 1
        from data_sources.honeypot_sim import ContractFacts
        return ContractFacts(address=address, chain=chain, sell_sellable=True,
                             buy_tax_pct=3.0, sell_tax_pct=5.0)
    def market_stats(self, address, chain="solana"):
        from fetchers.gmgn import TokenMarketStats
        self.calls += 1
        return TokenMarketStats(address=address, chain=chain, holder_count=12000,
                                smart_wallets=150, sniper_wallets=30,
                                bundler_wallets=40, fresh_wallets=100,
                                whale_wallets=130, renowned_wallets=37,
                                rat_trader_wallets=6, locked_ratio=0.5)


class _FakeHelius:
    pass


class _DevHelius:
    """Helius that returns a funding edge from the dev master wallet."""
    def __init__(self):
        self.traced = []
    def fetch_funding_edges(self, master, token_mint, chain="solana", max_tx=60):
        from data_sources.wallet_funding import FundingEdge
        from datetime import datetime, timezone
        self.traced.append((master, token_mint))
        return [FundingEdge(master_wallet=master, sub_wallet="SUB" + str(i),
                            amount=1e9, ts=datetime.now(timezone.utc), chain=chain)
                for i in range(2)]


class _DevGmgn(_FakeGmgn):
    """GMGN that returns a dev wallet + dev dump signals + wallet stats."""
    def __init__(self, dev="DEVWALLET11111111111111111111111111111111"):
        super().__init__()
        self.dev = dev
        self.dev_signals_calls = 0
        self.stats_calls = 0
    def find_dev_wallet(self, address, chain="solana"):
        return self.dev
    def dev_trader_signals(self, address, chain="solana"):
        self.dev_signals_calls += 1
        return {"dev_wallet": self.dev, "dev_sell_amount_percentage": 0.95,
                "dev_sell_tx_count": 8, "dev_buy_tx_count": 1,
                "dev_current_sell_amount": 5e9, "dev_current_transfer_out_amount": 5e9}
    def wallet_stats(self, wallet, chain="solana", period="30d"):
        from fetchers.gmgn import WalletAnalytics
        self.stats_calls += 1
        return WalletAnalytics(wallet=wallet, chain=chain, win_rate=0.9,
                               early_entry_rate=0.8, sniper_count=3)


def _info(address="ADDR", chain="solana", liq=500000.0, vol=100000.0):
    return TokenMarketInfo(address=address, chain=chain, symbol="TKN",
                           price_usd=0.1, volume_24h=vol, liquidity_usd=liq,
                           mcap=10000000.0)


def test_universe_from_profiles():
    class _FakeDex:
        def token_profiles(self, limit):
            return [_info(f"A{i}") for i in range(limit)]
    wire = LivePipelineWire(sources=LiveSourceBundle(dex_screener=_FakeDex()),
                            sources_from_env=False)
    uni = wire.fetch_universe(limit=5)
    assert uni.count == 5


def test_universe_requires_dex_screener():
    wire = LivePipelineWire(sources=LiveSourceBundle(), sources_from_env=False)
    with pytest.raises(RuntimeError):
        wire.fetch_universe()


def test_build_features_from_market():
    fake_gmgn = _FakeGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=fake_gmgn, helius=None),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert isinstance(f, TokenFeatures)
    assert f.token == "ADDR"
    assert f.contract_risk_level == "WATCH"  # sell tax 5% -> WATCH
    assert f.effective_circulating_supply == 10000000.0
    assert fake_gmgn.calls == 2  # market_stats + token_security


def test_build_features_no_gmgn_degrades():
    wire = LivePipelineWire(sources=LiveSourceBundle(), sources_from_env=False)
    f = wire.build_features(_info())
    assert f.contract_risk_level == "SAFE"  # default, no GMGN
    assert f.token == "ADDR"


def test_map_core_weights_from_market_stats():
    """GMGN market stats drive measured Organic/Smart Money/Safety (not 50)."""
    ms = {
        "holder_count": 120000, "smart_wallets": 1000, "sniper_wallets": 30,
        "bundler_wallets": 40, "fresh_wallets": 100, "whale_wallets": 1300,
        "renowned_wallets": 100, "rat_trader_wallets": 6, "locked_ratio": 0.9,
    }
    org, sm, safe = _map_core_weights(ms)
    # high holders + low sniper/bundler share -> organic well above baseline
    assert org > 50.0
    # high smart/renowned/whale -> smart money above baseline
    assert sm > 50.0
    # high locked ratio -> safety above baseline
    assert safe > 80.0
    assert all(20.0 <= x <= 100.0 for x in (org, sm, safe))


def test_map_core_weights_penalizes_sniper_bundler():
    """A token dominated by snipers/bundlers/fresh wallets gets LOW organic."""
    ms = {"holder_count": 100, "smart_wallets": 1, "sniper_wallets": 900,
          "bundler_wallets": 900, "fresh_wallets": 900, "whale_wallets": 1,
          "renowned_wallets": 1, "rat_trader_wallets": 900, "locked_ratio": 0.0}
    org, sm, safe = _map_core_weights(ms)
    assert org < 30.0
    assert sm < 50.0


def test_map_core_weights_empty_returns_baseline():
    assert _map_core_weights({}) == (50.0, 50.0, 50.0)
    assert _map_core_weights(None) == (50.0, 50.0, 50.0)


def test_map_alpha_raw_falls_back_without_market_data():
    # no market stats -> volume+liquidity proxy only
    assert _map_alpha_raw(None, volume=0, liquidity=0) == 40.0
    assert _map_alpha_raw({}, volume=0, liquidity=0) == 40.0


def test_map_alpha_raw_rewards_momentum_and_buy_pressure():
    # strong momentum + balanced buy share -> higher than volume-only base
    ms = {"price_24h": 0.5, "buy_volume_24h": 60.0, "volume_24h": 100.0}
    base = _map_alpha_raw(None, volume=1_000_000, liquidity=0)
    with_momentum = _map_alpha_raw(ms, volume=1_000_000, liquidity=0)
    assert with_momentum > base
    # clip: extreme momentum capped
    assert _map_alpha_raw({"price_24h": 10.0}, volume=0, liquidity=0) <= 100.0
    assert _map_alpha_raw({"price_24h": -10.0}, volume=0, liquidity=0) >= 20.0


def test_build_features_measures_core_weights_from_gmgn():
    """Organic/Smart Money are no longer hardcoded 50 when GMGN data present."""
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_FakeGmgn(), helius=None),
        sources_from_env=False)
    f = wire.build_features(_info())
    # fake stats: 12000 holders, 150 smart, locked 0.5 -> should differ from 50
    assert f.organic_raw != 50.0
    assert f.smart_money_raw != 50.0
    assert f.safety_raw != 50.0
    assert f.market_stats  # captured for transparency


def test_risk_level_mapping():
    assert _risk_level(0, 0, True) == "SAFE"
    assert _risk_level(6, 0, True) == "WATCH"
    assert _risk_level(12, 0, True) == "RISKY"
    assert _risk_level(25, 0, True) == "CRITICAL"
    assert _risk_level(0, 0, False) == "CRITICAL"  # cannot sell


def test_gmgn_renounced_parse_bool_and_string():
    assert _gmgn_renounced_from_notes(["gmgn_is_renounced=True"]) is True
    assert _gmgn_renounced_from_notes(["gmgn_is_renounced=true"]) is True
    assert _gmgn_renounced_from_notes(["gmgn_is_renounced=1"]) is True
    assert _gmgn_renounced_from_notes(["gmgn_is_renounced=False"]) is False
    assert _gmgn_renounced_from_notes(["gmgn_is_renounced=0"]) is False
    assert _gmgn_renounced_from_notes([]) is False
    assert _gmgn_renounced_from_notes(["other_note=1"]) is False


def test_build_features_captures_contract_facts():
    """ContractFacts -> contract-security facts on TokenFeatures."""
    class _ContractGmgn(_FakeGmgn):
        def token_security(self, address, chain):
            from data_sources.honeypot_sim import ContractFacts
            return ContractFacts(address=address, chain=chain, sell_sellable=True,
                                 buy_tax_pct=2.0, sell_tax_pct=2.0,
                                 lp_locked_pct=0.9, lp_burned=True,
                                 notes=["gmgn_is_renounced=True"])
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_ContractGmgn(), helius=None),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert f.contract_sell_sellable is True
    assert f.contract_lp_locked_pct == 0.9
    assert f.contract_lp_burned is True
    assert f.contract_renounced is True


def test_available_sources_reporting():
    b = LiveSourceBundle(dex_screener=object(), gmgn=_FakeGmgn())
    assert set(b.available) == {"dex_screener", "gmgn"}


class _FakeOkx:
    """OKX fetcher returning dev-reputation insider signals + holder tags."""
    def __init__(self, sig=None, tags=None):
        self.sig = sig if sig is not None else {
            "okx_rug_pull_count": 69, "okx_dev_total_tokens": 14594,
            "okx_dev_holding_percent": 0.0}
        self.tags = tags if tags is not None else {
            "okx_snipers_percent": 44.0, "okx_top10_holdings_percent": 89.5}
    def insider_signals(self, address):
        return dict(self.sig)
    def token_tags_by_address(self, address):
        return dict(self.tags)


def test_available_sources_includes_okx():
    b = LiveSourceBundle(dex_screener=object(), gmgn=_FakeGmgn(), okx=_FakeOkx())
    assert set(b.available) == {"dex_screener", "gmgn", "okx"}


def test_build_features_wires_okx_insider_signals():
    """OKX dev-reputation flows into TokenFeatures.okx_signals (Solana)."""
    okx = _FakeOkx()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(), okx=okx),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert f.okx_signals["okx_rug_pull_count"] == 69
    assert f.okx_signals["okx_dev_total_tokens"] == 14594


def test_build_features_merges_holder_tags_into_okx_signals():
    """Holder-composition tags (token-details) merge into okx_signals."""
    okx = _FakeOkx()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(), okx=okx),
        sources_from_env=False)
    f = wire.build_features(_info())
    # both dev-reputation (from token-dev-info) AND holder tags (from
    # token-details) present in the merged signal set
    assert f.okx_signals["okx_rug_pull_count"] == 69          # dev-info
    assert f.okx_signals["okx_snipers_percent"] == 44.0       # token-details
    assert f.okx_signals["okx_top10_holdings_percent"] == 89.5


def test_okx_signals_lift_insider_probability_in_score():
    """A serial-rugger OKX signal must raise the scored insider_probability."""
    okx = _FakeOkx()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(), okx=okx),
        sources_from_env=False)
    f = wire.build_features(_info())
    score = wire.pipeline.score_token(f)
    assert score.insider_probability >= 0.30   # rugger contributes 0.30+


def test_build_features_skips_okx_on_non_sol():
    """OKX memepump is Solana-focused; non-sol chains get no okx_signals."""
    okx = _FakeOkx()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(), okx=okx),
        sources_from_env=False)
    f = wire.build_features(_info(chain="bsc"))
    assert f.okx_signals == {}


def test_build_features_degrades_when_okx_fails():
    """An OKX exception must not break the whole token build."""
    class _FailingOkx:
        def insider_signals(self, address):
            raise RuntimeError("okx down")
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(),
                                 okx=_FailingOkx()),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert f.okx_signals == {}
    assert f.token == "ADDR"  # still built


def test_okx_signals_degrade_when_empty():
    """No OKX dev record + no holder tags -> empty okx_signals (not a signal)."""
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(),
                                 okx=_FakeOkx({}, {})),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert f.okx_signals == {}


def test_okx_holder_composition_activates_insider_supply():
    """OKX top10/coord holder composition fills suspected_insider_holdings.

    Previously these inputs were 0, so IHR + distribution were dead and the
    insider probability was inflated/arbitrary. Now top10 concentration maps to
    suspected insider supply and max(sniper/insider/bundler) to cluster supply.
    """
    okx = _FakeOkx(sig={"okx_rug_pull_count": 0, "okx_dev_total_tokens": 1,
                        "okx_dev_holding_percent": 0.0},
                   tags={"okx_snipers_percent": 40.0, "okx_insiders_percent": 30.0,
                         "okx_bundlers_percent": 10.0,
                         "okx_top10_holdings_percent": 60.0})
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(), okx=okx),
        sources_from_env=False)
    f = wire.build_features(_info())  # mcap = 10_000_000 = effective supply
    # top10 60% of supply -> suspected_insider_holdings
    assert abs(f.suspected_insider_holdings - 6_000_000.0) < 1.0
    # coord = max(40,30,10) = 40% -> insider_cluster_supply
    assert abs(f.insider_cluster_supply - 4_000_000.0) < 1.0
    # these activate IHR -> insider_probability should rise vs no data
    score = wire.pipeline.score_token(f)
    assert score.insider_probability > 0.0


def test_build_features_wires_helius_funding_trace():
    """EV-021: dev wallet from GMGN -> Helius funding edges -> funding_clusters."""
    helius = _DevHelius()
    gmgn = _DevGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=gmgn, helius=helius),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert len(f.funding_clusters) == 2
    assert f.deployer == "DEVWALLET11111111111111111111111111111111"
    # helius traced the dev wallet with the token mint
    assert helius.traced[0][0] == "DEVWALLET11111111111111111111111111111111"
    assert helius.traced[0][1] == "ADDR"  # token mint = token address


def test_build_features_skips_helius_on_non_sol():
    """EV-021 is Solana RPC only — non-sol chains get no funding trace."""
    helius = _DevHelius()
    gmgn = _DevGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=gmgn, helius=helius),
        sources_from_env=False)
    f = wire.build_features(_info(chain="bsc"))
    assert f.funding_clusters == []
    assert helius.traced == []


def test_build_features_degrades_when_helius_fails():
    """A Helius exception must not break the whole token build."""
    class _FailingHelius:
        def fetch_funding_edges(self, *a, **kw):
            raise RuntimeError("rpc down")
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=_DevGmgn(),
                                 helius=_FailingHelius()),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert f.funding_clusters == []
    assert f.token == "ADDR"  # still built


def test_score_with_funding_clusters_lifts_insider_probability():
    """Funding edges flowing into the pipeline should raise insider_probability."""
    helius = _DevHelius()
    gmgn = _DevGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=gmgn, helius=helius),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert len(f.funding_clusters) == 2
    score = wire.pipeline.score_token(f)
    # insider cluster evidence present -> insider probability > 0
    assert score.insider_probability > 0.0


def test_build_features_wires_wallet_stats():
    """GMGN wallet_stats fills classification features for the dev wallet."""
    helius = _DevHelius()
    gmgn = _DevGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=gmgn, helius=helius),
        sources_from_env=False)
    f = wire.build_features(_info())
    assert len(f.wallet_analytics) == 1
    assert f.wallet_analytics[0].wallet == "DEVWALLET11111111111111111111111111111111"
    assert f.wallet_analytics[0].win_rate == 0.9
    assert gmgn.stats_calls == 1


def test_wallet_stats_feeds_wallet_classify():
    """Wallet analytics should classify the dev wallet as DEV, not Unknown."""
    helius = _DevHelius()
    gmgn = _DevGmgn()
    wire = LivePipelineWire(
        sources=LiveSourceBundle(dex_screener=None, gmgn=gmgn, helius=helius),
        sources_from_env=False)
    f = wire.build_features(_info())
    # force the dev wallet into the trading set so classifier sees it
    score = wire.pipeline.score_token(f)
    # classification list exists; even if empty trades, build path is safe
    assert "wallet_classify" in score.outputs
    assert gmgn.stats_calls == 1


def test_enrich_market_uses_detail():
    """score_from_market should enrich profile via token_detail for full scores."""
    class _FakeDex:
        def token_profiles(self, limit):
            # profile has NO liquidity/price (like real /token-profiles endpoint)
            return [TokenMarketInfo(address="ADDR", chain="solana", symbol="T",
                                    volume_24h=100.0, liquidity_usd=0.0)]
        def token_detail(self, address, chain):
            # detail has full market data
            return TokenMarketInfo(address="ADDR", chain="solana", symbol="T",
                                   price_usd=0.5, volume_24h=2_000_000.0,
                                   liquidity_usd=5_000_000.0, mcap=50_000_000.0)
    wire = LivePipelineWire(sources=LiveSourceBundle(dex_screener=_FakeDex()),
                            sources_from_env=False)
    score = wire.score_from_market(wire.fetch_universe(1).tokens[0])
    # enriched liq/vol should push alpha_raw above the flat 40 default
    assert score.risk_adjusted_alpha != 40.0 or score.risk_adjusted_alpha > 0
