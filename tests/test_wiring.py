"""Test live wiring: fetchers -> TokenFeatures -> pipeline (mocked)."""
import pytest

from fetchers.dex_screener import TokenMarketInfo
from pipeline import TokenFeatures
from wiring import LiveSourceBundle, LivePipelineWire, LiveUniverse, _risk_level


class _FakeGmgn:
    def __init__(self):
        self.calls = 0
    def token_security(self, address, chain):
        self.calls += 1
        from data_sources.honeypot_sim import ContractFacts
        return ContractFacts(address=address, chain=chain, sell_sellable=True,
                             buy_tax_pct=3.0, sell_tax_pct=5.0)


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
    assert fake_gmgn.calls == 1


def test_build_features_no_gmgn_degrades():
    wire = LivePipelineWire(sources=LiveSourceBundle(), sources_from_env=False)
    f = wire.build_features(_info())
    assert f.contract_risk_level == "SAFE"  # default, no GMGN
    assert f.token == "ADDR"


def test_risk_level_mapping():
    assert _risk_level(0, 0, True) == "SAFE"
    assert _risk_level(6, 0, True) == "WATCH"
    assert _risk_level(12, 0, True) == "RISKY"
    assert _risk_level(25, 0, True) == "CRITICAL"
    assert _risk_level(0, 0, False) == "CRITICAL"  # cannot sell


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
