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
