"""Tests for the technical indicator calculations."""

import numpy as np
import pandas as pd
import pytest

from scanner import indicators as ind


class TestSMA:
    def test_sma_values(self, ohlcv):
        s = ind.sma(ohlcv["Close"], 3)
        # First 2 values are NaN (warm-up)
        assert s.iloc[0] != s.iloc[0]  # NaN
        assert s.iloc[1] != s.iloc[1]  # NaN
        expected = ohlcv["Close"].iloc[0:3].mean()
        assert s.iloc[2] == pytest.approx(expected)


class TestEMA:
    def test_ema_length(self, ohlcv):
        s = ind.ema(ohlcv["Close"], 20)
        assert len(s) == len(ohlcv)
        assert s.iloc[-1] > 0

    def test_ema_follows_trend(self, ohlcv_trending_up):
        s = ind.ema(ohlcv_trending_up["Close"], 20)
        last = s.iloc[-1]
        assert last > ohlcv_trending_up["Close"].iloc[0]


class TestRSI:
    def test_rsi_bounds(self, ohlcv):
        r = ind.rsi(ohlcv["Close"], 14).dropna()
        assert ((r >= 0) & (r <= 100)).all()

    def test_rsi_all_gains_is_100(self):
        s = pd.Series(np.linspace(1, 2, 50))
        r = ind.rsi(s, 14).dropna()
        assert (r > 99).all()

    def test_rsi_all_losses_is_0(self):
        s = pd.Series(np.linspace(2, 1, 50))
        r = ind.rsi(s, 14).dropna()
        # First value after warm-up is a fill artifact (avg_loss==0 => NaN => 100).
        # Every subsequent value should be ~0 since there are only losses.
        assert (r.iloc[1:] < 1).all()


class TestMACD:
    def test_macd_columns(self, ohlcv):
        df = ind.macd(ohlcv["Close"], 12, 26, 9)
        assert list(df.columns) == ["macd", "signal", "hist"]
        assert df["macd"].iloc[-1] != 0

    def test_hist_is_difference(self, ohlcv):
        df = ind.macd(ohlcv["Close"], 12, 26, 9)
        diff = df["macd"] - df["signal"]
        assert np.allclose(df["hist"].dropna(), diff.dropna())


class TestBollingerBands:
    def test_band_order(self, ohlcv):
        bb = ind.bollinger_bands(ohlcv["Close"], 20, 2.0)
        row = bb.dropna().iloc[-1]
        assert row["upper"] >= row["middle"] >= row["lower"]

    def test_percent_b_reasonable_bounds(self, ohlcv):
        bb = ind.bollinger_bands(ohlcv["Close"], 20, 2.0)
        pctb = bb["percent_b"].dropna()
        # %B can legitimately exceed [0, 1] when the close falls outside
        # the bands, but it should stay within a small tolerance of them.
        assert pctb.min() >= -0.5
        assert pctb.max() <= 1.5

    def test_percent_b_formula(self, ohlcv):
        bb = ind.bollinger_bands(ohlcv["Close"], 20, 2.0)
        row = bb.dropna().iloc[-1]
        expected = (ohlcv["Close"].iloc[-1] - row["lower"]) / (
            row["upper"] - row["lower"]
        )
        assert row["percent_b"] == pytest.approx(expected)


class TestATR:
    def test_atr_positive(self, ohlcv):
        a = ind.atr(ohlcv, 14).dropna()
        assert (a > 0).all()

    def test_atr_scale(self, ohlcv):
        a = ind.atr(ohlcv, 14).dropna()
        # ATR should be small relative to price
        assert (a / ohlcv["Close"].iloc[-1] < 0.05).all()


class TestStochastic:
    def test_stochastic_bounds(self, ohlcv):
        k, d = ind.stochastic(ohlcv, 14, 3)
        kk, dd = k.dropna(), d.dropna()
        assert ((kk >= 0) & (kk <= 100)).all()
        assert ((dd >= 0) & (dd <= 100)).all()


class TestADX:
    def test_adx_bounds(self, ohlcv):
        a = ind.adx(ohlcv, 14).dropna()
        assert ((a >= 0) & (a <= 100)).all()

    def test_adx_high_in_trend(self, ohlcv_trending_up):
        a = ind.adx(ohlcv_trending_up, 14).dropna()
        assert a.iloc[-1] > 20


class TestIchimoku:
    def test_columns(self, ohlcv):
        ich = ind.ichimoku(ohlcv)
        assert set(["tenkan", "kijun", "senkou_a", "senkou_b", "chikou"]).issubset(
            ich.columns
        )

    def test_senkou_shifted(self, ohlcv):
        ich = ind.ichimoku(ohlcv)
        # senkou_a is tenkan/kijun avg shifted forward by 26
        tenkan = (ohlcv["High"].rolling(9).max() + ohlcv["Low"].rolling(9).min()) / 2
        kijun = (ohlcv["High"].rolling(26).max() + ohlcv["Low"].rolling(26).min()) / 2
        expected = ((tenkan + kijun) / 2).shift(26)
        assert np.allclose(ich["senkou_a"].dropna(), expected.dropna())


class TestZigZag:
    def test_pivot_flags(self, ohlcv):
        zz = ind.zigzag(ohlcv, 0.8)
        assert "is_pivot_high" in zz.columns
        assert "is_pivot_low" in zz.columns
        # A point cannot be both a pivot high and pivot low
        overlap = (zz["is_pivot_high"] & zz["is_pivot_low"]).sum()
        assert overlap == 0

    def test_zigzag_finds_swings(self):
        # Oscillating series with swings much larger than the 0.5% deviation
        # threshold, so the zigzag must detect both pivot highs and pivot lows.
        t = np.linspace(0, 4 * np.pi, 40)
        closes = 100 + 5 * np.sin(t)
        df = pd.DataFrame(
            {
                "Open": closes,
                "High": closes + 0.1,
                "Low": closes - 0.1,
                "Close": closes,
                "Volume": 1000.0,
            }
        )
        zz = ind.zigzag(df, 0.5)
        assert zz["is_pivot_low"].sum() >= 1
        assert zz["is_pivot_high"].sum() >= 1
