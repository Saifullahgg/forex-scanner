"""Tests for the trading strategies."""

import numpy as np
import pandas as pd
import pytest

from scanner.strategies import (
    BollingerBounce,
    IchimokuCloud,
    MACDStrategy,
    MovingAverageCrossover,
    RSIMeanReversion,
    Signal,
    StochasticStrategy,
    SupportResistance,
    TrendContinuation,
)


def _df_with(columns: dict, n: int = 5) -> pd.DataFrame:
    """Build a small DataFrame with the given columns filled over n rows."""
    data = {}
    for name, val in columns.items():
        if isinstance(val, (list, tuple)):
            data[name] = list(val) + [val[-1]] * (n - len(val))
        else:
            data[name] = [val] * n
    return pd.DataFrame(data)


class TestSignal:
    def test_strength_clamped(self):
        s = Signal("BUY", 1.5)
        assert s.strength == 1.0
        s = Signal("BUY", -0.5)
        assert s.strength == 0.0

    def test_default_reasons(self):
        s = Signal("NEUTRAL", 0.1)
        assert s.reasons == []


class TestMovingAverageCrossover:
    def test_uptrend_buy(self):
        df = _df_with(
            {
                "Close": [100.0, 101.0, 102.0],
                "ema_20": [99.0, 100.0, 101.0],
                "ema_50": [100.0, 100.0, 100.0],
            },
            n=5,
        )
        sig = MovingAverageCrossover(20, 50).generate(df)
        assert sig.action == "BUY"

    def test_downtrend_sell(self):
        # Last Close must be below ema_50 for the downtrend branch to fire
        # (it requires Close < slow EMA, not just fast < slow).
        df = _df_with(
            {
                "Close": [102.0, 101.0, 100.0, 99.0],
                "ema_20": [101.0, 100.0, 99.0, 98.0],
                "ema_50": [100.0, 100.0, 100.0, 100.0],
            },
            n=5,
        )
        sig = MovingAverageCrossover(20, 50).generate(df)
        assert sig.action == "SELL"

    def test_missing_columns_neutral(self):
        df = _df_with({"Close": [100.0]})
        sig = MovingAverageCrossover(20, 50).generate(df)
        assert sig.action == "NEUTRAL"


class TestRSIMeanReversion:
    def test_oversold_buy(self):
        df = _df_with({"Close": [100.0], "rsi_14": [25.0]})
        sig = RSIMeanReversion(14).generate(df)
        assert sig.action == "BUY"

    def test_overbought_sell(self):
        df = _df_with({"Close": [100.0], "rsi_14": [75.0]})
        sig = RSIMeanReversion(14).generate(df)
        assert sig.action == "SELL"

    def test_neutral(self):
        df = _df_with({"Close": [100.0], "rsi_14": [50.0]})
        sig = RSIMeanReversion(14).generate(df)
        assert sig.action == "NEUTRAL"


class TestMACDStrategy:
    def test_bullish_cross_buy(self):
        df = _df_with(
            {
                "Close": [100.0],
                "macd_12_26_9_macd": [0.10, 0.12],
                "macd_12_26_9_signal": [0.12, 0.11],
                "macd_12_26_9_hist": [0.01, 0.02],
            }
        )
        sig = MACDStrategy(12, 26, 9).generate(df)
        assert sig.action in ("BUY", "NEUTRAL")

    def test_bearish_cross_sell(self):
        df = _df_with(
            {
                "Close": [100.0],
                "macd_12_26_9_macd": [0.12, 0.10],
                "macd_12_26_9_signal": [0.11, 0.12],
                "macd_12_26_9_hist": [-0.01, -0.02],
            }
        )
        sig = MACDStrategy(12, 26, 9).generate(df)
        assert sig.action in ("SELL", "NEUTRAL")

    def test_missing_columns_neutral(self):
        df = _df_with({"Close": [100.0]})
        sig = MACDStrategy(12, 26, 9).generate(df)
        assert sig.action == "NEUTRAL"


class TestBollingerBounce:
    def test_lower_band_buy(self):
        df = _df_with(
            {
                "Close": [100.0],
                "bb_20_2.0_upper": [110.0],
                "bb_20_2.0_lower": [90.0],
                "bb_20_2.0_middle": [100.0],
                "bb_20_2.0_percent_b": [0.01],
            }
        )
        sig = BollingerBounce(20, 2.0).generate(df)
        assert sig.action == "BUY"

    def test_upper_band_sell(self):
        df = _df_with(
            {
                "Close": [100.0],
                "bb_20_2.0_upper": [110.0],
                "bb_20_2.0_lower": [90.0],
                "bb_20_2.0_middle": [100.0],
                "bb_20_2.0_percent_b": [0.99],
            }
        )
        sig = BollingerBounce(20, 2.0).generate(df)
        assert sig.action == "SELL"

    def test_missing_columns_neutral(self):
        df = _df_with({"Close": [100.0]})
        sig = BollingerBounce(20, 2.0).generate(df)
        assert sig.action == "NEUTRAL"


class TestStochasticStrategy:
    def test_bullish_cross_buy(self):
        df = _df_with(
            {
                "Close": [100.0],
                "stoch_k_14_3": [20.0, 22.0, 25.0, 28.0, 30.0],
                "stoch_d_14_3": [22.0, 24.0, 26.0, 27.0, 27.5],
            }
        )
        sig = StochasticStrategy(14, 3).generate(df)
        assert sig.action in ("BUY", "NEUTRAL")

    def test_bearish_cross_sell(self):
        df = _df_with(
            {
                "Close": [100.0],
                "stoch_k_14_3": [80.0, 78.0, 75.0, 72.0, 70.0],
                "stoch_d_14_3": [78.0, 76.0, 74.0, 73.0, 72.5],
            }
        )
        sig = StochasticStrategy(14, 3).generate(df)
        assert sig.action in ("SELL", "NEUTRAL")


class TestTrendContinuation:
    def test_strong_uptrend_buy(self):
        df = _df_with(
            {
                "Close": [102.0],
                "adx_14": [35.0],
                "ema_50": [100.0],
            }
        )
        sig = TrendContinuation(14, 25.0).generate(df)
        assert sig.action == "BUY"

    def test_strong_downtrend_sell(self):
        df = _df_with(
            {
                "Close": [98.0],
                "adx_14": [35.0],
                "ema_50": [100.0],
            }
        )
        sig = TrendContinuation(14, 25.0).generate(df)
        assert sig.action == "SELL"

    def test_ranging_neutral(self):
        df = _df_with({"Close": [100.0], "adx_14": [18.0], "ema_50": [100.0]})
        sig = TrendContinuation(14, 25.0).generate(df)
        assert sig.action == "NEUTRAL"


class TestSupportResistance:
    def test_testing_support_buy(self):
        df = pd.DataFrame(
            {
                "Close": [100.0, 101.0, 100.5],
                "is_pivot_high": [False, True, False],
                "is_pivot_low": [True, False, False],
                "zz_value": [99.0, 102.0, np.nan],
            }
        )
        sig = SupportResistance(0.8).generate(df)
        assert sig.action in ("BUY", "NEUTRAL")

    def test_testing_resistance_sell(self):
        df = pd.DataFrame(
            {
                "Close": [100.0, 101.0, 101.9],
                "is_pivot_high": [False, True, False],
                "is_pivot_low": [True, False, False],
                "zz_value": [99.0, 102.0, np.nan],
            }
        )
        sig = SupportResistance(0.8).generate(df)
        assert sig.action in ("SELL", "NEUTRAL")

    def test_missing_columns_neutral(self):
        df = _df_with({"Close": [100.0]})
        sig = SupportResistance(0.8).generate(df)
        assert sig.action == "NEUTRAL"


class TestIchimokuCloud:
    def test_bullish_setup_buy(self):
        df = _df_with(
            {
                "Close": [103.0],
                "ich_tenkan": [101.0, 102.0],
                "ich_kijun": [101.5, 101.5],
                "ich_senkou_a": [99.0],
                "ich_senkou_b": [98.0],
                "ich_chikou": [105.0],
            }
        )
        sig = IchimokuCloud().generate(df)
        assert sig.action in ("BUY", "NEUTRAL")

    def test_bearish_setup_sell(self):
        df = _df_with(
            {
                "Close": [97.0],
                "ich_tenkan": [100.0, 99.0],
                "ich_kijun": [99.5, 99.5],
                "ich_senkou_a": [101.0],
                "ich_senkou_b": [102.0],
                "ich_chikou": [95.0],
            }
        )
        sig = IchimokuCloud().generate(df)
        assert sig.action in ("SELL", "NEUTRAL")

    def test_missing_columns_neutral(self):
        df = _df_with({"Close": [100.0]})
        sig = IchimokuCloud().generate(df)
        assert sig.action == "NEUTRAL"
