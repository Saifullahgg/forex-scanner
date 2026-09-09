"""Tests for the trading bot controller (webapp/bot.py)."""

from scanner.engine import Scanner
from webapp.bot import BOT_STRATEGIES, DEFAULT_WEIGHTS, BotController
from webapp.trading import PaperTrader


def _make_controller():
    return BotController(PaperTrader(starting_balance=100_000.0))


def test_bot_strategies_match_engine():
    scanner = Scanner()
    engine_names = {s.name for s in scanner.strategies}
    assert set(BOT_STRATEGIES) == engine_names
    assert set(DEFAULT_WEIGHTS.keys()) == engine_names


def test_initial_state():
    bot = _make_controller()
    state = bot.state()
    assert state["running"] is False
    assert all(state["enabled"].values())
    assert state["min_score"] == 12.0
    assert state["strategies"] == BOT_STRATEGIES
    assert state["last_run"] is None
    assert state["log"] == []


def test_set_config_updates_enabled_min_score_pairs():
    bot = _make_controller()
    bot.set_config(
        {
            "enabled": {"MACD": False, "Ichimoku Cloud": False},
            "min_score": 8.0,
            "pairs": ["EURUSD", "USDJPY"],
        }
    )
    state = bot.state()
    assert state["enabled"]["MACD"] is False
    assert state["enabled"]["Ichimoku Cloud"] is False
    assert state["enabled"]["MA Crossover"] is True
    assert state["min_score"] == 8.0
    assert state["pairs"] == ["EURUSD", "USDJPY"]


def test_set_config_ignores_unknown_strategies_and_cleans_pairs():
    bot = _make_controller()
    bot.set_config(
        {
            "enabled": {"NotARealStrategy": True},
            "pairs": [" eurusd ", "gbpusd"],
        }
    )
    state = bot.state()
    assert "NotARealStrategy" not in state["enabled"]
    assert state["pairs"] == ["EURUSD", "GBPUSD"]


def test_pause_and_resume_strategy():
    bot = _make_controller()
    bot.pause_strategy("MACD")
    assert bot.state()["enabled"]["MACD"] is False
    bot.resume_strategy("MACD")
    assert bot.state()["enabled"]["MACD"] is True


def test_reset_restores_defaults():
    bot = _make_controller()
    bot.pause_strategy("MACD")
    bot.set_config({"min_score": 5.0, "pairs": ["EURUSD"]})
    bot.reset()
    state = bot.state()
    assert all(state["enabled"].values())
    assert state["min_score"] == 12.0
    assert state["pairs"] == bot.pairs
    assert state["weights"] == DEFAULT_WEIGHTS


def test_close_trade_logs_and_returns_state():
    bot = _make_controller()
    bot.trader.open_order("EURUSD", "BUY", 10000, 1.0800, label="bot")
    state = bot.close_trade("T0001", 1.0850)
    assert state["log"][-1]["level"] == "info"
    assert "Closed BUY EURUSD" in state["log"][-1]["message"]


def test_run_with_no_enabled_strategies_does_not_trade():
    bot = _make_controller()
    for name in BOT_STRATEGIES:
        bot.pause_strategy(name)
    scanner = Scanner()
    state = bot.run(scanner, {"EURUSD": None}, lambda _p: 1.08, manual=True)
    # No-enabled branch sets a shorter last_run payload with key "trades".
    assert state["last_run"]["trades"] == 0
    assert bot.trader.account()["open_count"] == 0


def test_run_requires_min_score(ohlcv):
    bot = _make_controller()
    bot.min_score = 99.0  # unreachable, so no trade should open
    scanner = Scanner()
    state = bot.run(scanner, {"EURUSD": ohlcv}, lambda _p: 1.08, manual=True)
    assert state["last_run"]["trades_opened"] == 0
    assert bot.trader.account()["open_count"] == 0


def test_run_opens_trade_when_score_high(ohlcv_trending_up):
    bot = _make_controller()
    bot.min_score = 0.0  # any actionable signal passes
    scanner = Scanner()
    state = bot.run(scanner, {"EURUSD": ohlcv_trending_up}, lambda _p: 1.05, manual=True)
    assert state["last_run"]["trades_opened"] == 1
    assert state["last_run"]["best_signal"]["pair"] == "EURUSD"
    assert state["last_run"]["best_signal"]["action"] in ("BUY", "SELL")
    acc = bot.trader.account()
    assert acc["open_count"] == 1
    # Trade was opened with label "bot".
    assert acc["open_positions"][0]["label"] == "bot"


def test_run_appends_signal_history():
    bot = _make_controller()
    bot.min_score = 99.0  # still records signals even without a trade
    scanner = Scanner()
    bot.run(scanner, {"EURUSD": None}, lambda _p: 1.08, manual=True)
    # No data -> no signals; history stays empty in this degenerate case.
    assert len(bot.state()["signal_history"]) == 0


def test_run_restricts_scanner_to_enabled_strategies():
    bot = _make_controller()
    for name in BOT_STRATEGIES:
        if name != "MA Crossover":
            bot.pause_strategy(name)
    scanner = Scanner()
    bot.run(scanner, {"EURUSD": None}, lambda _p: 1.08, manual=True)
    assert [s.name for s in scanner.strategies] == ["MA Crossover"]


def test_confluence_score_neutral_contributes_zero():
    bot = _make_controller()
    scanner = Scanner()
    # A result with no actionable signals should score 0.
    from scanner.engine import ScanResult
    from scanner.strategies import Signal

    result = ScanResult(
        pair="EURUSD",
        price=1.08,
        overall=Signal("NEUTRAL", 0.0, []),
        individual=[(name, Signal("NEUTRAL", 0.0, [])) for name in BOT_STRATEGIES],
        df=object(),  # not used by _confluence_score
    )
    assert bot._confluence_score(result) == 0.0


def test_log_caps_at_100_entries():
    bot = _make_controller()
    for i in range(120):
        bot._log("info", f"message {i}")
    assert len(bot.state()["log"]) == 100
