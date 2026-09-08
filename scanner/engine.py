"""
Core scanner engine: computes indicators, runs strategies,
and aggregates signals into an overall recommendation.
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd

from . import indicators as ind
from .strategies import (
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


class ScanResult:
    """Result of scanning a single currency pair."""

    def __init__(
        self,
        pair: str,
        price: float,
        overall: Signal,
        individual: List[Tuple[str, Signal]],
        df: pd.DataFrame,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ):
        self.pair = pair
        self.price = price
        self.overall = overall
        self.individual = individual
        self.df = df
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    @property
    def rr_ratio(self) -> Optional[float]:
        """Risk/reward ratio based on SL/TP distances from price."""
        if self.stop_loss is None or self.take_profit is None:
            return None
        risk = abs(self.price - self.stop_loss)
        reward = abs(self.take_profit - self.price)
        if risk <= 0:
            return None
        return round(reward / risk, 2)

    @property
    def buy_votes(self) -> int:
        return sum(1 for _, s in self.individual if s.action == "BUY")

    @property
    def sell_votes(self) -> int:
        return sum(1 for _, s in self.individual if s.action == "SELL")

    @property
    def neutral_votes(self) -> int:
        return sum(1 for _, s in self.individual if s.action == "NEUTRAL")

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "price": self.price,
            "action": self.overall.action,
            "strength": round(self.overall.strength, 3),
            "buy_votes": self.buy_votes,
            "sell_votes": self.sell_votes,
            "neutral_votes": self.neutral_votes,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "rr_ratio": self.rr_ratio,
            "reasons": self.overall.reasons,
            "signals": [
                {"strategy": name, "action": s.action, "strength": round(s.strength, 3), "reasons": s.reasons}
                for name, s in self.individual
            ],
        }


class Scanner:
    """Runs all configured strategies against fetched data."""

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self.ema_fast = config.get("ema_fast", 20)
        self.ema_slow = config.get("ema_slow", 50)
        self.rsi_period = config.get("rsi_period", 14)
        self.macd_fast = config.get("macd_fast", 12)
        self.macd_slow = config.get("macd_slow", 26)
        self.macd_signal = config.get("macd_signal", 9)
        self.bb_period = config.get("bb_period", 20)
        self.bb_std = config.get("bb_std", 2.0)
        self.stoch_k = config.get("stoch_k", 14)
        self.stoch_d = config.get("stoch_d", 3)
        self.adx_period = config.get("adx_period", 14)
        self.adx_threshold = config.get("adx_threshold", 25.0)
        self.zz_deviation = config.get("zz_deviation", 0.8)
        self.sl_atr_mult = config.get("sl_atr_mult", 1.5)
        self.tp_atr_mult = config.get("tp_atr_mult", 2.5)

        self.strategies = [
            MovingAverageCrossover(self.ema_fast, self.ema_slow),
            RSIMeanReversion(self.rsi_period),
            MACDStrategy(self.macd_fast, self.macd_slow, self.macd_signal),
            BollingerBounce(self.bb_period, self.bb_std),
            StochasticStrategy(self.stoch_k, self.stoch_d),
            TrendContinuation(self.adx_period, self.adx_threshold),
            SupportResistance(self.zz_deviation),
            IchimokuCloud(),
        ]

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicator columns to the DataFrame."""
        out = df.copy()

        out[f"ema_{self.ema_fast}"] = ind.ema(out["Close"], self.ema_fast)
        out[f"ema_{self.ema_slow}"] = ind.ema(out["Close"], self.ema_slow)

        out[f"rsi_{self.rsi_period}"] = ind.rsi(out["Close"], self.rsi_period)

        macd_df = ind.macd(out["Close"], self.macd_fast, self.macd_slow, self.macd_signal)
        prefix = f"macd_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}"
        out[f"{prefix}_macd"] = macd_df["macd"]
        out[f"{prefix}_signal"] = macd_df["signal"]
        out[f"{prefix}_hist"] = macd_df["hist"]

        bb_df = ind.bollinger_bands(out["Close"], self.bb_period, self.bb_std)
        bb_prefix = f"bb_{self.bb_period}_{self.bb_std}"
        out[f"{bb_prefix}_upper"] = bb_df["upper"]
        out[f"{bb_prefix}_lower"] = bb_df["lower"]
        out[f"{bb_prefix}_middle"] = bb_df["middle"]
        out[f"{bb_prefix}_bandwidth"] = bb_df["bandwidth"]
        out[f"{bb_prefix}_percent_b"] = bb_df["percent_b"]

        k, d = ind.stochastic(out, self.stoch_k, self.stoch_d)
        out[f"stoch_k_{self.stoch_k}_{self.stoch_d}"] = k
        out[f"stoch_d_{self.stoch_k}_{self.stoch_d}"] = d

        out[f"adx_{self.adx_period}"] = ind.adx(out, self.adx_period)

        zz = ind.zigzag(out, self.zz_deviation)
        out["zz_value"] = zz["zz_value"]
        out["is_pivot_high"] = zz["is_pivot_high"]
        out["is_pivot_low"] = zz["is_pivot_low"]

        out["atr_14"] = ind.atr(out, 14)

        ich = ind.ichimoku(out)
        out["ich_tenkan"] = ich["tenkan"]
        out["ich_kijun"] = ich["kijun"]
        out["ich_senkou_a"] = ich["senkou_a"]
        out["ich_senkou_b"] = ich["senkou_b"]
        out["ich_chikou"] = ich["chikou"]

        return out

    def scan_pair(self, df: pd.DataFrame) -> ScanResult:
        """Run all strategies on a single pair's data."""
        if df is None or len(df) < 60:
            raise ValueError("Insufficient data to scan")

        full = self.compute_indicators(df)
        # Drop rows with NaN indicators for stability
        cols_needed = [
            f"ema_{self.ema_fast}",
            f"ema_{self.ema_slow}",
            f"rsi_{self.rsi_period}",
            f"stoch_k_{self.stoch_k}_{self.stoch_d}",
            f"stoch_d_{self.stoch_k}_{self.stoch_d}",
            f"adx_{self.adx_period}",
        ]
        clean = full.dropna(subset=cols_needed).reset_index(drop=True)
        if len(clean) < 10:
            raise ValueError("Not enough clean data after indicator warm-up")

        price = float(clean.iloc[-1]["Close"])

        individual: List[Tuple[str, Signal]] = []
        buy_strength, sell_strength = 0.0, 0.0
        buy_count, sell_count = 0, 0

        for strat in self.strategies:
            try:
                sig = strat.generate(clean)
            except Exception as exc:  # noqa: BLE001
                sig = Signal("NEUTRAL", 0.0, [f"Strategy error: {exc}"])
            individual.append((strat.name, sig))
            if sig.action == "BUY":
                buy_strength += sig.strength
                buy_count += 1
            elif sig.action == "SELL":
                sell_strength += sig.strength
                sell_count += 1

        # Aggregate: weighted vote
        total = max(buy_count + sell_count, 1)
        if buy_count > sell_count:
            action = "BUY"
            strength = (buy_strength / total) * (1 + (buy_count - sell_count) / max(total, 1))
        elif sell_count > buy_count:
            action = "SELL"
            strength = (sell_strength / total) * (1 + (sell_count - buy_count) / max(total, 1))
        else:
            action = "NEUTRAL"
            strength = max(buy_strength, sell_strength) / total

        # Require at least 2 aligned signals to fire a trade signal
        reasons = []
        if action == "BUY" and buy_count >= 2:
            reasons.append(f"{buy_count}/{len(self.strategies)} strategies bullish")
        elif action == "SELL" and sell_count >= 2:
            reasons.append(f"{sell_count}/{len(self.strategies)} strategies bearish")
        else:
            action = "NEUTRAL"
            strength *= 0.5
            reasons.append("No clear consensus (need 2+ aligned signals)")

        overall = Signal(action, min(strength, 1.0), reasons)

        # ATR-based stop loss / take profit (only for actionable signals)
        stop_loss, take_profit = None, None
        if action in ("BUY", "SELL"):
            atr_val = float(clean["atr_14"].iloc[-1])
            sl_dist = self.sl_atr_mult * atr_val
            tp_dist = self.tp_atr_mult * atr_val
            if action == "BUY":
                stop_loss = round(price - sl_dist, 6)
                take_profit = round(price + tp_dist, 6)
            else:
                stop_loss = round(price + sl_dist, 6)
                take_profit = round(price - tp_dist, 6)

        return ScanResult(
            "", price, overall, individual, clean,
            stop_loss=stop_loss, take_profit=take_profit,
        )

    def scan_many(self, data: Dict[str, pd.DataFrame]) -> List[ScanResult]:
        """Scan multiple pairs from a {pair: df} dict."""
        results = []
        for pair, df in data.items():
            if df is None:
                continue
            try:
                res = self.scan_pair(df)
                res.pair = pair
                results.append(res)
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] {pair}: scan failed: {exc}")
        return results
