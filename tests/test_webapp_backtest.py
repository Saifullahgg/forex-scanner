"""Tests for the walk-forward backtester (webapp/backtest.py)."""

import pytest

from scanner.engine import Scanner
from webapp.backtest import BacktestResult, BacktestTrade, _aggregate, run_backtest
from webapp.trading import pip_size


def test_insufficient_data_raises():
    with pytest.raises(ValueError, match="Insufficient data"):
        run_backtest(None, Scanner(), "EURUSD", "1h")


def test_too_short_frame_raises():
    import pandas as pd

    tiny = pd.DataFrame(
        {"Open": [1.0] * 10, "High": [1.0] * 10, "Low": [1.0] * 10,
         "Close": [1.0] * 10, "Volume": [100.0] * 10},
        index=pd.date_range("2024-01-01", periods=10, freq="h"),
    )
    with pytest.raises(ValueError, match="Insufficient data"):
        run_backtest(tiny, Scanner(), "EURUSD", "1h")


def test_max_candles_limits_work_window(ohlcv):
    scanner = Scanner()
    res = run_backtest(ohlcv, scanner, "EURUSD", "1h", max_candles=100)
    assert res.candles_used <= 100
    assert res.pair == "EURUSD"
    assert res.interval == "1h"


def test_run_backtest_returns_dataclass(ohlcv):
    res = run_backtest(ohlcv, Scanner(), "EURUSD", "1h")
    assert isinstance(res, BacktestResult)
    assert isinstance(res.stats, dict)
    assert isinstance(res.verdict, dict)
    assert res.stats["trades"] == len(res.trades)
    assert res.candles_used > 0


def test_trade_has_expected_fields(ohlcv_trending_up):
    # A strong uptrend should generate at least one BUY trade.
    res = run_backtest(ohlcv_trending_up, Scanner(), "EURUSD", "1h")
    assert len(res.trades) > 0
    t = res.trades[0]
    assert isinstance(t, BacktestTrade)
    assert t.pair == "EURUSD"
    assert t.side in ("BUY", "SELL")
    assert t.entry > 0 and t.exit > 0
    assert t.entry_time < t.exit_time
    assert t.bars_held >= 0
    # SL/TP must bracket a BUY entry or straddle a SELL entry.
    if t.side == "BUY":
        assert t.sl < t.entry < t.tp
    else:
        assert t.sl > t.entry > t.tp


def test_stats_empty_when_no_trades():
    result = BacktestResult(pair="EURUSD", interval="1h", candles_used=100, trades=[])
    s = result.stats
    assert s["trades"] == 0
    assert s["win_rate"] is None
    assert s["total_pips"] == 0.0
    assert s["profit_factor"] is None


def test_stats_with_trades():
    trades = [
        BacktestTrade("EURUSD", "BUY", 1.08, 1.09, "t0", "t1", pnl_pips=10.0, pnl_pct=0.9, sl=1.07, tp=1.10, bars_held=5),
        BacktestTrade("EURUSD", "BUY", 1.08, 1.06, "t2", "t3", pnl_pips=-20.0, pnl_pct=-1.8, sl=1.07, tp=1.10, bars_held=3),
        BacktestTrade("EURUSD", "SELL", 1.08, 1.079, "t4", "t5", pnl_pips=10.0, pnl_pct=0.1, sl=1.09, tp=1.07, bars_held=2),
    ]
    result = BacktestResult(pair="EURUSD", interval="1h", candles_used=100, trades=trades)
    s = result.stats
    assert s["trades"] == 3
    assert s["win_rate"] == pytest.approx(66.7, rel=0.1)
    assert s["total_pips"] == 0.0
    assert s["largest_win"] == 10.0
    assert s["largest_loss"] == -20.0
    assert s["expected_value"] == pytest.approx(0.0, rel=0.5)
    # gross win = 20, gross loss = 20 -> profit factor 1.0
    assert s["profit_factor"] == pytest.approx(1.0, abs=0.01)


def test_verdict_thresholds():
    no_trades = BacktestResult("EURUSD", "1h", 100, [])
    assert no_trades.verdict["label"] == "NO TRADES"

    trades_wr70 = [
        BacktestTrade("X", "BUY", 1, 1.001, "a", "b", pnl_pips=1, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1)
        for _ in range(7)
    ] + [
        BacktestTrade("X", "BUY", 1, 0.999, "a", "b", pnl_pips=-1, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1)
        for _ in range(3)
    ]
    r70 = BacktestResult("EURUSD", "1h", 100, trades_wr70)
    assert r70.stats["win_rate"] == 70.0
    assert r70.verdict["label"] == "STRONG EDGE"


def test_verdict_no_edge():
    trades = [
        BacktestTrade("X", "BUY", 1, 1.001, "a", "b", pnl_pips=1, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1),
        BacktestTrade("X", "BUY", 1, 0.999, "a", "b", pnl_pips=-1, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1),
    ]
    result = BacktestResult("EURUSD", "1h", 100, trades)
    assert result.stats["win_rate"] == 50.0
    assert result.verdict["label"] == "NO EDGE"


def test_equity_curve_is_cumulative():
    trades = [
        BacktestTrade("X", "BUY", 1, 1.001, "t0", "t1", pnl_pips=10, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1),
        BacktestTrade("X", "BUY", 1, 0.999, "t1", "t2", pnl_pips=-5, pnl_pct=0, sl=0.9, tp=1.1, bars_held=1),
    ]
    result = BacktestResult("EURUSD", "1h", 100, trades)
    curve = result.equity_curve
    assert curve == [{"exit_time": "t1", "equity": 10.0}, {"exit_time": "t2", "equity": 5.0}]


def test_to_dict_shape(ohlcv):
    res = run_backtest(ohlcv, Scanner(), "EURUSD", "1h")
    d = res.to_dict()
    assert d["pair"] == "EURUSD"
    assert d["interval"] == "1h"
    assert set(d.keys()) == {"pair", "interval", "candles_used", "stats", "verdict", "equity_curve", "trades"}
    if d["trades"]:
        first = d["trades"][0]
        assert set(first.keys()) == {
            "pair", "side", "entry", "exit", "entry_time", "exit_time",
            "pnl_pips", "pnl_pct", "sl", "tp", "bars_held",
        }


def test_aggregate_buy_when_majority_bullish(ohlcv):
    scanner = Scanner()
    # Give the scanner a strategy that fires BUY with strength 0.9.
    from scanner.strategies import Signal

    class FakeBuy:
        name = "FakeBuy"

        def generate(self, df):
            return Signal("BUY", 0.9, ["bull"])

    scanner.strategies = [FakeBuy(), FakeBuy(), FakeBuy()]
    action, price = _aggregate(scanner, ohlcv)
    assert action == "BUY"
    assert price > 0
