"""Tests for the scanner engine (indicator computation + consensus)."""

import pandas as pd
import pytest

from scanner.engine import ScanResult, Scanner
from scanner.strategies import Signal


class TestComputeIndicators:
    def test_all_columns_present(self, ohlcv):
        scanner = Scanner()
        out = scanner.compute_indicators(ohlcv)

        expected = [
            "ema_20",
            "ema_50",
            "rsi_14",
            "macd_12_26_9_macd",
            "macd_12_26_9_signal",
            "macd_12_26_9_hist",
            "bb_20_2.0_upper",
            "bb_20_2.0_lower",
            "bb_20_2.0_middle",
            "bb_20_2.0_bandwidth",
            "bb_20_2.0_percent_b",
            "stoch_k_14_3",
            "stoch_d_14_3",
            "adx_14",
            "atr_14",
            "zz_value",
            "is_pivot_high",
            "is_pivot_low",
            "ich_tenkan",
            "ich_kijun",
            "ich_senkou_a",
            "ich_senkou_b",
            "ich_chikou",
        ]
        for col in expected:
            assert col in out.columns, f"Missing indicator column: {col}"


class TestScanPair:
    def test_insufficient_data_raises(self):
        scanner = Scanner()
        small = pd.DataFrame(
            {"Open": [1.0] * 10, "High": [1.0] * 10, "Low": [1.0] * 10,
             "Close": [1.0] * 10, "Volume": [1.0] * 10}
        )
        with pytest.raises(ValueError):
            scanner.scan_pair(small)

    def test_returns_scan_result(self, ohlcv):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv)
        assert isinstance(res, ScanResult)
        assert res.price > 0
        assert res.overall.action in ("BUY", "SELL", "NEUTRAL")
        assert 0.0 <= res.overall.strength <= 1.0

    def test_individual_strategies_present(self, ohlcv):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv)
        assert len(res.individual) == len(scanner.strategies)
        names = [name for name, _ in res.individual]
        assert "Ichimoku Cloud" in names

    def test_sl_tp_only_for_signals(self, ohlcv):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv)
        if res.overall.action == "NEUTRAL":
            assert res.stop_loss is None
            assert res.take_profit is None
        else:
            assert res.stop_loss is not None
            assert res.take_profit is not None
            if res.overall.action == "BUY":
                assert res.stop_loss < res.price < res.take_profit
            else:
                assert res.take_profit < res.price < res.stop_loss

    def test_buy_signal_on_uptrend(self, ohlcv_trending_up):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv_trending_up)
        assert res.overall.action in ("BUY", "NEUTRAL")

    def test_sell_signal_on_downtrend(self, ohlcv_trending_down):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv_trending_down)
        assert res.overall.action in ("SELL", "NEUTRAL")


class TestScanMany:
    def test_scan_multiple_pairs(self, ohlcv_trending_up, ohlcv_trending_down):
        scanner = Scanner()
        data = {"EURUSD": ohlcv_trending_up, "GBPUSD": ohlcv_trending_down}
        results = scanner.scan_many(data)
        assert len(results) == 2
        assert {r.pair for r in results} == {"EURUSD", "GBPUSD"}

    def test_skips_none_data(self, ohlcv):
        scanner = Scanner()
        data = {"EURUSD": ohlcv, "GBPUSD": None}
        results = scanner.scan_many(data)
        assert len(results) == 1
        assert results[0].pair == "EURUSD"


class TestScanResult:
    def test_to_dict(self, ohlcv):
        scanner = Scanner()
        res = scanner.scan_pair(ohlcv)
        d = res.to_dict()
        assert d["pair"] == ""
        assert d["action"] in ("BUY", "SELL", "NEUTRAL")
        assert "stop_loss" in d
        assert "take_profit" in d
        assert "rr_ratio" in d
        assert isinstance(d["signals"], list)
        assert len(d["signals"]) == len(res.individual)

    def test_votes(self):
        individual = [
            ("S1", Signal("BUY", 0.5)),
            ("S2", Signal("BUY", 0.5)),
            ("S3", Signal("SELL", 0.5)),
            ("S4", Signal("NEUTRAL", 0.1)),
        ]
        res = ScanResult("EURUSD", 1.08, Signal("BUY", 0.6), individual, None)
        assert res.buy_votes == 2
        assert res.sell_votes == 1
        assert res.neutral_votes == 1

    def test_rr_ratio(self):
        individual = [("S1", Signal("BUY", 0.5))]
        res = ScanResult("EURUSD", 1.08000, Signal("BUY", 0.6), individual, None,
                         stop_loss=1.07000, take_profit=1.09500)
        assert res.rr_ratio == 1.5
