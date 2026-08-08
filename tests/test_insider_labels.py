"""Test insider-outcome labeling (backtest/insider_labels.py)."""
import pytest

from backtest.insider_labels import (InsiderOutcome, classify_insider_outcome,
                                     classify_okx_outcome, label_from_gmgn,
                                     label_from_okx)


def test_rug_from_honeypot():
    sig = {"is_honeypot": True, "dev_sell_amount_percentage": 0.0}
    assert classify_insider_outcome(sig) == InsiderOutcome.RUG


def test_rug_dev_dump_with_unlocked_lp():
    sig = {"is_honeypot": False, "dev_sell_amount_percentage": 0.9,
           "dev_sell_tx_count": 10, "dev_buy_tx_count": 1, "lp_locked_pct": 0.1}
    assert classify_insider_outcome(sig) == InsiderOutcome.RUG


def test_dev_dump_net_seller():
    sig = {"is_honeypot": False, "dev_sell_amount_percentage": 0.75,
           "dev_sell_tx_count": 12, "dev_buy_tx_count": 2, "lp_locked_pct": 0.9,
           "top_10_holder_rate": 0.05}
    assert classify_insider_outcome(sig) == InsiderOutcome.DEV_DUMP


def test_dev_dump_requires_net_seller():
    # dev sold a lot but bought MORE (accumulating, not dumping)
    sig = {"is_honeypot": False, "dev_sell_amount_percentage": 0.9,
           "dev_sell_tx_count": 2, "dev_buy_tx_count": 10, "lp_locked_pct": 0.9}
    assert classify_insider_outcome(sig) != InsiderOutcome.DEV_DUMP


def test_early_sell_concentrated_with_outflow():
    sig = {"is_honeypot": False, "dev_sell_amount_percentage": 0.1,
           "dev_sell_tx_count": 1, "dev_buy_tx_count": 1,
           "top_10_holder_rate": 0.6, "dev_current_sell_amount": 1e6,
           "dev_current_transfer_out_amount": 5e6, "lp_locked_pct": 0.9}
    assert classify_insider_outcome(sig) == InsiderOutcome.EARLY_SELL


def test_clean_when_distributed_no_dev_activity():
    sig = {"is_honeypot": False, "dev_sell_amount_percentage": 0.1,
           "dev_sell_tx_count": 1, "dev_buy_tx_count": 2,
           "top_10_holder_rate": 0.2, "dev_current_sell_amount": 1e6,
           "dev_current_transfer_out_amount": 1e5, "lp_locked_pct": 0.9}
    assert classify_insider_outcome(sig) == InsiderOutcome.CLEAN


def test_label_from_gmgn_maps_security_fields():
    out = label_from_gmgn(
        token="TOKEN", chain="solana",
        dev_signals={"dev_wallet": "W", "dev_sell_amount_percentage": 0.95,
                     "dev_sell_tx_count": 8, "dev_buy_tx_count": 1,
                     "dev_current_transfer_out_amount": 9e9},
        security={"is_honeypot": False, "renounced": True,
                  "top_10_holder_rate": "0.5",
                  "lock_summary": {"lock_percent": 0.05}})
    assert out.token == "TOKEN"
    assert out.outcome == InsiderOutcome.RUG  # dev dumped + LP ~5% locked
    assert out.signals["lp_locked_pct"] == pytest.approx(0.05)


def test_label_from_gmgn_missing_security_defaults():
    out = label_from_gmgn(token="T", chain="sol",
                          dev_signals={}, security={})
    assert out.outcome == InsiderOutcome.CLEAN
    # no security data -> cannot assume LP secure -> lp_locked_pct stays 0.0
    assert out.signals["lp_locked_pct"] == 0.0
    assert out.signals["lp_burned"] is False


# --- OKX Onchain OS labels ---

def test_okx_rug_from_rug_pull_count():
    sig = {"okx_rug_pull_count": 3, "okx_dev_total_tokens": 9,
           "okx_dev_holding_percent": 5.0, "okx_snipers_percent": 10.0,
           "okx_top10_holdings_percent": 60.0}
    assert classify_okx_outcome(sig) == InsiderOutcome.RUG


def test_okx_dev_dump_sold_off_with_coordination():
    sig = {"okx_rug_pull_count": 0, "okx_dev_total_tokens": 5,
           "okx_dev_holding_percent": 8.0, "okx_snipers_percent": 44.0,
           "okx_insiders_percent": 0.0, "okx_bundlers_percent": 0.0,
           "okx_top10_holdings_percent": 60.0}
    assert classify_okx_outcome(sig) == InsiderOutcome.DEV_DUMP


def test_okx_early_sell_high_top10_with_coordination():
    sig = {"okx_rug_pull_count": 0, "okx_dev_total_tokens": 3,
           "okx_dev_holding_percent": 44.0, "okx_insiders_percent": 10.0,
           "okx_snipers_percent": 44.0, "okx_bundlers_percent": 0.0,
           "okx_top10_holdings_percent": 89.5}
    assert classify_okx_outcome(sig) == InsiderOutcome.EARLY_SELL


def test_okx_dev_dump_requires_coordination():
    # dev sold off but no insider/sniper/bundler coordination -> not dev_dump
    sig = {"okx_rug_pull_count": 0, "okx_dev_total_tokens": 5,
           "okx_dev_holding_percent": 8.0, "okx_snipers_percent": 0.0,
           "okx_insiders_percent": 0.0, "okx_bundlers_percent": 0.0,
           "okx_top10_holdings_percent": 10.0}
    assert classify_okx_outcome(sig) != InsiderOutcome.DEV_DUMP


def test_okx_clean_when_no_signals():
    sig = {"okx_rug_pull_count": 0, "okx_dev_total_tokens": 0,
           "okx_dev_holding_percent": 0.0, "okx_insiders_percent": 0.0,
           "okx_snipers_percent": 0.0, "okx_bundlers_percent": 0.0,
           "okx_top10_holdings_percent": 1.0}
    assert classify_okx_outcome(sig) == InsiderOutcome.CLEAN


def test_label_from_okx_merges_dev_and_tags():
    out = label_from_okx(
        token="TOKEN", chain="solana",
        dev_signals={"okx_rug_pull_count": 2.0, "okx_dev_total_tokens": 4.0,
                     "okx_dev_holding_percent": 3.0},
        tags_signals={"okx_snipers_percent": 55.0,
                      "okx_top10_holdings_percent": 80.0})
    assert out.outcome == InsiderOutcome.RUG  # rug_pull_count >= 1 wins
    assert out.signals["okx_snipers_percent"] == 55.0
