"""Tests for the in-memory paper trading store (webapp/trading.py)."""

import pytest

from webapp.trading import PaperTrader, pip_size


def test_pip_size():
    assert pip_size(150.0) == 0.01  # JPY-quoted
    assert pip_size(1.08) == 0.0001  # 4-digit
    assert pip_size(50.0) == 0.01  # boundary
    assert pip_size(49.99) == 0.0001


def test_account_initial_state():
    trader = PaperTrader(starting_balance=100_000.0)
    acc = trader.account()
    assert acc["mode"] == "paper"
    assert acc["balance"] == 100_000.0
    assert acc["equity"] == 100_000.0
    assert acc["open_count"] == 0
    assert acc["closed_count"] == 0
    assert acc["win_rate"] is None
    assert acc["total_pnl"] == 0.0


def test_open_order_buy():
    trader = PaperTrader()
    pos = trader.open_order("EURUSD", "BUY", 10000, 1.08, sl=1.07, tp=1.10)
    assert pos["id"] == "T0001"
    assert pos["side"] == "BUY"
    assert pos["pair"] == "EURUSD"
    assert pos["open_price"] == 1.08
    assert pos["sl"] == 1.07
    assert pos["tp"] == 1.10
    assert pos["margin"] == pytest.approx(10000 * 1.08, rel=1e-6)
    assert pos["label"] == "demo"

    acc = trader.account()
    assert acc["open_count"] == 1
    assert acc["margin_used"] == pytest.approx(10800.0, rel=1e-6)


def test_open_order_invalid_side():
    trader = PaperTrader()
    with pytest.raises(ValueError, match="BUY or SELL"):
        trader.open_order("EURUSD", "HOLD", 10000, 1.08)


def test_open_order_invalid_units():
    trader = PaperTrader()
    with pytest.raises(ValueError, match="positive"):
        trader.open_order("EURUSD", "BUY", 0, 1.08)


def test_open_order_sequential_ids():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 1, 1.08)
    trader.open_order("GBPUSD", "SELL", 1, 1.27)
    assert list(trader.positions.keys()) == ["T0001", "T0002"]


def test_close_buy_profit():
    trader = PaperTrader(starting_balance=100_000.0)
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    trade = trader.close_position("T0001", 1.0850)
    assert trade is not None
    # (1.0850 - 1.0800) * 10000 = 50.0
    assert trade["pnl"] == pytest.approx(50.0, abs=1e-2)
    # (0.0050 / 0.0001) = 50 pips
    assert trade["pnl_pips"] == pytest.approx(50.0, abs=1e-6)
    assert trade["side"] == "BUY"

    acc = trader.account()
    assert acc["balance"] == pytest.approx(100_050.0, rel=1e-6)
    assert acc["open_count"] == 0
    assert acc["closed_count"] == 1
    assert acc["total_pnl"] == pytest.approx(50.0, rel=1e-6)
    assert acc["win_rate"] == 100.0


def test_close_sell_profit_with_jpy_pips():
    trader = PaperTrader()
    trader.open_order("USDJPY", "SELL", 1000, 150.00)
    trade = trader.close_position("T0001", 149.50)
    assert trade["pnl"] == pytest.approx(500.0, rel=1e-6)  # (150 - 149.5) * 1000
    # (0.50 / 0.01) = 50 pips for JPY pair
    assert trade["pnl_pips"] == pytest.approx(50.0, abs=1e-6)


def test_close_nonexistent_returns_none():
    trader = PaperTrader()
    assert trader.close_position("T9999", 1.08) is None


def test_account_marks_open_positions_to_market():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    acc = trader.account(prices={"EURUSD": 1.0850})
    assert acc["open_count"] == 1
    assert acc["unrealized_pnl"] == pytest.approx(50.0, rel=1e-6)
    assert acc["equity"] == pytest.approx(100_050.0, rel=1e-6)
    pos = acc["open_positions"][0]
    assert pos["current_price"] == pytest.approx(1.0850, rel=1e-6)
    assert pos["unrealized_pnl"] == pytest.approx(50.0, rel=1e-6)


def test_account_without_prices_falls_back_to_entry():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    acc = trader.account()
    assert acc["unrealized_pnl"] == 0.0
    assert acc["equity"] == acc["balance"]


def test_close_all_uses_price_fn():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    trader.open_order("GBPUSD", "SELL", 10000, 1.2700)
    closed = trader.close_all(lambda pair: {"EURUSD": 1.0850, "GBPUSD": 1.2650}[pair])
    assert closed == 2
    assert trader.account()["open_count"] == 0


def test_close_all_skips_missing_prices():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    closed = trader.close_all(lambda _pair: None)
    assert closed == 0
    assert trader.account()["open_count"] == 1


def test_reset_restores_initial_state():
    trader = PaperTrader(starting_balance=50_000.0)
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    trader.close_position("T0001", 1.0850)
    trader.reset()
    acc = trader.account()
    assert acc["balance"] == 50_000.0
    assert acc["open_count"] == 0
    assert acc["closed_count"] == 0
    assert acc["total_pnl"] == 0.0
    # Sequence counter resets so ids restart.
    trader.open_order("EURUSD", "BUY", 1, 1.08)
    assert list(trader.positions.keys()) == ["T0001"]


def test_monthly_summary_groups_by_month():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 10000, 1.0800)
    trader.close_position("T0001", 1.0850)  # +50
    trader.open_order("GBPUSD", "SELL", 10000, 1.2700)
    trader.close_position("T0002", 1.2750)  # -50 (sold high, bought back higher)

    summary = trader.monthly_summary()
    assert len(summary["months"]) == 1
    month = summary["months"][0]
    assert month["trades"] == 2
    assert month["wins"] == 1
    assert month["losses"] == 1
    assert month["net_pnl"] == pytest.approx(0.0, rel=1e-6)
    assert month["win_rate"] == 50.0


def test_monthly_summary_empty():
    trader = PaperTrader()
    assert trader.monthly_summary() == {"months": []}


def test_history_is_newest_first():
    trader = PaperTrader()
    trader.open_order("EURUSD", "BUY", 1, 1.0800)
    trader.close_position("T0001", 1.0810)
    trader.open_order("GBPUSD", "BUY", 1, 1.2700)
    trader.close_position("T0002", 1.2710)
    history = trader.account()["history"]
    assert [h["pair"] for h in history] == ["GBPUSD", "EURUSD"]


def test_win_rate_and_total_pnl_with_mixed_results():
    trader = PaperTrader(starting_balance=1000.0)
    trader.open_order("AUDUSD", "BUY", 100, 0.6500)
    trader.close_position("T0001", 0.6520)  # +20 * ... = +0.002*100 = 0.2
    trader.open_order("NZDUSD", "BUY", 100, 0.6100)
    trader.close_position("T0002", 0.6080)  # -0.002*100 = -0.2
    acc = trader.account()
    assert acc["closed_count"] == 2
    assert acc["win_rate"] == 50.0
    assert acc["total_pnl"] == pytest.approx(0.0, rel=1e-6)
