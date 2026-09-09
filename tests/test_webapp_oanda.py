"""Tests for the OANDA-ready adapter (webapp/oanda.py)."""

import pytest

from webapp.oanda import OandaAdapter
from webapp.trading import PaperTrader


@pytest.fixture
def trader():
    return PaperTrader(starting_balance=100_000.0)


@pytest.fixture
def adapter(trader):
    return OandaAdapter(trader)


def test_defaults_to_paper_mode(adapter):
    assert adapter.connected is False
    assert adapter.mode == "paper"
    assert adapter.env in ("practice", "live")


def test_status_merges_account_snapshot(adapter):
    status = adapter.status()
    assert status["mode"] == "paper"
    assert status["connected"] is False
    assert status["currency"] == "USD"
    # Paper account fields flow through.
    assert status["balance"] == 100_000.0
    assert status["open_count"] == 0


def test_order_in_paper_mode_opens_position(adapter):
    pos = adapter.order("EURUSD", "BUY", 10000, 1.08)
    assert pos["id"] == "T0001"
    assert pos["label"] == "oanda"
    assert adapter.trader.account()["open_count"] == 1


def test_close_in_paper_mode_closes_position(adapter):
    adapter.order("EURUSD", "SELL", 10000, 1.08)
    result = adapter.close("T0001", 1.07)
    assert result["closed"] is True
    assert result["trade"]["pnl"] == pytest.approx(100.0, rel=1e-6)


def test_close_missing_position_reports_not_closed(adapter):
    result = adapter.close("T9999", 1.08)
    assert result["closed"] is False
    assert result["trade"] is None


def test_prices_build_bid_ask_mid(adapter):
    quotes = adapter.prices(["EURUSD", "USDJPY"], lambda pair: {"EURUSD": 1.0800, "USDJPY": 150.00}[pair])
    assert quotes["mode"] == "paper"
    assert set(quotes["quotes"].keys()) == {"EURUSD", "USDJPY"}
    for q in quotes["quotes"].values():
        assert set(q.keys()) == {"bid", "ask", "mid", "spread"}
        assert q["bid"] < q["ask"]
        assert q["mid"] == pytest.approx((q["bid"] + q["ask"]) / 2, rel=1e-6)
        assert q["spread"] > 0


def test_prices_skip_pairs_with_no_feed(adapter):
    quotes = adapter.prices(["EURUSD", "XXXYYY"], lambda pair: 1.08 if pair == "EURUSD" else None)
    assert list(quotes["quotes"].keys()) == ["EURUSD"]


def test_live_mode_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("OANDA_API_KEY", "test-key")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "101-001-1234567-001")
    adapter = OandaAdapter(PaperTrader())
    assert adapter.connected is True
    assert adapter.mode == "live"
    with pytest.raises(NotImplementedError):
        adapter.order("EURUSD", "BUY", 10000, 1.08)
    with pytest.raises(NotImplementedError):
        adapter.close("T0001", 1.08)
