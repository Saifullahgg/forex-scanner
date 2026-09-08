"""
Trading strategies for the Forex Signal Scanner.

Each strategy analyzes a DataFrame of OHLCV data plus pre-computed
indicator columns, and returns a Signal.

A Signal is a NamedTuple:
    - action: "BUY", "SELL", or "NEUTRAL"
    - strength: float 0.0-1.0 (conviction)
    - reasons: list of strings describing why
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Signal:
    action: str  # BUY / SELL / NEUTRAL
    strength: float  # 0.0 - 1.0
    reasons: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.strength = max(0.0, min(1.0, self.strength))


class BaseStrategy:
    name = "base"

    def generate(self, df) -> Signal:
        raise NotImplementedError


class MovingAverageCrossover(BaseStrategy):
    """Golden cross / death cross on EMA fast vs EMA slow."""

    name = "MA Crossover"

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow

    def generate(self, df) -> Signal:
        fast_col = f"ema_{self.fast}"
        slow_col = f"ema_{self.slow}"
        if fast_col not in df or slow_col not in df:
            return Signal("NEUTRAL", 0.0, ["Missing MA columns"])

        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = last["Close"]

        if prev[fast_col] <= prev[slow_col] and last[fast_col] > last[slow_col]:
            return Signal(
                "BUY",
                0.8,
                [
                    f"Golden cross: EMA{self.fast} crossed above EMA{self.slow}",
                    f"Price {price:.5f} above slow EMA {last[slow_col]:.5f}",
                ],
            )
        if prev[fast_col] >= prev[slow_col] and last[fast_col] < last[slow_col]:
            return Signal(
                "SELL",
                0.8,
                [
                    f"Death cross: EMA{self.fast} crossed below EMA{self.slow}",
                    f"Price {price:.5f} below slow EMA {last[slow_col]:.5f}",
                ],
            )

        # Trend continuation
        if last[fast_col] > last[slow_col] and last["Close"] > last[slow_col]:
            return Signal("BUY", 0.45, ["Uptrend: fast EMA above slow EMA"])
        if last[fast_col] < last[slow_col] and last["Close"] < last[slow_col]:
            return Signal("SELL", 0.45, ["Downtrend: fast EMA below slow EMA"])

        return Signal("NEUTRAL", 0.1, ["EMAs flat / mixed"])


class RSIMeanReversion(BaseStrategy):
    """Buy oversold, sell overbought."""

    name = "RSI Mean Reversion"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate(self, df) -> Signal:
        col = f"rsi_{self.period}"
        if col not in df:
            return Signal("NEUTRAL", 0.0, ["Missing RSI column"])

        last = df.iloc[-1]
        prev = df.iloc[-2]
        rsi_val = last[col]

        reasons = [f"RSI({self.period}) = {rsi_val:.1f}"]

        if rsi_val < self.oversold:
            # Check reversal (rising off oversold)
            if prev[col] < self.oversold and rsi_val > prev[col]:
                return Signal("BUY", 0.7, reasons + ["RSI rising out of oversold zone"])
            return Signal("BUY", 0.4, reasons + ["RSI in oversold zone"])
        if rsi_val > self.overbought:
            if prev[col] > self.overbought and rsi_val < prev[col]:
                return Signal("SELL", 0.7, reasons + ["RSI falling out of overbought zone"])
            return Signal("SELL", 0.4, reasons + ["RSI in overbought zone"])

        return Signal("NEUTRAL", 0.1, reasons + ["RSI neutral zone"])


class MACDStrategy(BaseStrategy):
    """MACD line / signal crossovers + histogram momentum."""

    name = "MACD"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate(self, df) -> Signal:
        prefix = f"macd_{self.fast}_{self.slow}_{self.signal}"
        m_col, s_col, h_col = f"{prefix}_macd", f"{prefix}_signal", f"{prefix}_hist"
        if m_col not in df:
            return Signal("NEUTRAL", 0.0, ["Missing MACD columns"])

        last = df.iloc[-1]
        prev = df.iloc[-2]
        macd_val = last[m_col]
        sig_val = last[s_col]
        hist_val = last[h_col]
        prev_hist = prev[h_col]

        reasons = [f"MACD {macd_val:.5f}, Signal {sig_val:.5f}"]

        if prev[m_col] <= prev[s_col] and macd_val > sig_val:
            return Signal(
                "BUY",
                0.75,
                reasons
                + [f"Bullish MACD cross (hist rising: {prev_hist:.5f} -> {hist_val:.5f})"],
            )
        if prev[m_col] >= prev[s_col] and macd_val < sig_val:
            return Signal(
                "SELL",
                0.75,
                reasons
                + [f"Bearish MACD cross (hist falling: {prev_hist:.5f} -> {hist_val:.5f})"],
            )

        # Momentum continuation
        if macd_val > sig_val and hist_val > prev_hist:
            return Signal("BUY", 0.5, reasons + ["MACD above signal, histogram expanding"])
        if macd_val < sig_val and hist_val < prev_hist:
            return Signal("SELL", 0.5, reasons + ["MACD below signal, histogram contracting"])

        return Signal("NEUTRAL", 0.1, reasons + ["MACD flat / converging"])


class BollingerBounce(BaseStrategy):
    """Price touch of Bollinger Bands with %b confirmation."""

    name = "Bollinger Bounce"

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def generate(self, df) -> Signal:
        prefix = f"bb_{self.period}_{self.std_dev}"
        upper, lower, mid, pctb = (
            f"{prefix}_upper",
            f"{prefix}_lower",
            f"{prefix}_middle",
            f"{prefix}_percent_b",
        )
        if upper not in df:
            return Signal("NEUTRAL", 0.0, ["Missing Bollinger columns"])

        last = df.iloc[-1]
        price = last["Close"]
        pctb_val = last[pctb]

        reasons = [f"%b = {pctb_val:.2f}"]

        if pctb_val < 0.02:
            return Signal("BUY", 0.6, reasons + ["Price at lower band (oversold extreme)"])
        if pctb_val > 0.98:
            return Signal("SELL", 0.6, reasons + ["Price at upper band (overbought extreme)"])

        # Mean reversion to middle band
        if pctb_val < 0.35 and price > last[lower]:
            return Signal("BUY", 0.4, reasons + ["Price below mid-band, mean-reverting"])
        if pctb_val > 0.65 and price < last[upper]:
            return Signal("SELL", 0.4, reasons + ["Price above mid-band, mean-reverting"])

        return Signal("NEUTRAL", 0.1, reasons + ["Price near mid-band"])


class StochasticStrategy(BaseStrategy):
    """Stochastic %K/%D crossovers."""

    name = "Stochastic"

    def __init__(self, k_period: int = 14, d_period: int = 3):
        self.k_period = k_period
        self.d_period = d_period

    def generate(self, df) -> Signal:
        k_col = f"stoch_k_{self.k_period}_{self.d_period}"
        d_col = f"stoch_d_{self.k_period}_{self.d_period}"
        if k_col not in df:
            return Signal("NEUTRAL", 0.0, ["Missing Stochastic columns"])

        last = df.iloc[-1]
        prev = df.iloc[-2]
        k, d = last[k_col], last[d_col]

        reasons = [f"%K={k:.1f}, %D={d:.1f}"]

        if prev[k_col] <= prev[d_col] and k > d and k < 30:
            return Signal("BUY", 0.65, reasons + ["Bullish %K cross below 30 (oversold)"])
        if prev[k_col] >= prev[d_col] and k < d and k > 70:
            return Signal("SELL", 0.65, reasons + ["Bearish %K cross above 70 (overbought)"])

        if prev[k_col] <= prev[d_col] and k > d:
            return Signal("BUY", 0.45, reasons + ["Bullish %K cross"])
        if prev[k_col] >= prev[d_col] and k < d:
            return Signal("SELL", 0.45, reasons + ["Bearish %K cross"])

        return Signal("NEUTRAL", 0.1, reasons + ["No stochastic cross"])


class TrendContinuation(BaseStrategy):
    """ADX + EMA trend filter for continuation entries."""

    name = "Trend Continuation"

    def __init__(self, adx_period: int = 14, adx_threshold: float = 25.0):
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def generate(self, df) -> Signal:
        adx_col = f"adx_{self.adx_period}"
        if adx_col not in df:
            return Signal("NEUTRAL", 0.0, ["Missing ADX column"])

        last = df.iloc[-1]
        adx_val = last[adx_col]
        close = last["Close"]
        ema50 = last.get("ema_50", close)

        reasons = [f"ADX({self.adx_period}) = {adx_val:.1f}"]

        if adx_val < self.adx_threshold:
            return Signal("NEUTRAL", 0.1, reasons + ["Market ranging (ADX low)"])

        if close > ema50:
            return Signal("BUY", 0.55, reasons + ["Strong uptrend, price above EMA50"])
        if close < ema50:
            return Signal("SELL", 0.55, reasons + ["Strong downtrend, price below EMA50"])

        return Signal("NEUTRAL", 0.2, reasons + ["Trend direction unclear"])


class SupportResistance(BaseStrategy):
    """Detect recent swing highs/lows (zigzag) and test them."""

    name = "Support / Resistance"

    def __init__(self, deviation_pct: float = 0.8, lookback: int = 120):
        self.deviation_pct = deviation_pct
        self.lookback = lookback

    def generate(self, df) -> Signal:
        if "is_pivot_high" not in df or "is_pivot_low" not in df:
            return Signal("NEUTRAL", 0.0, ["Missing zigzag columns"])

        window = df.iloc[-self.lookback :]
        piv_highs = window.loc[window["is_pivot_high"], "zz_value"]
        piv_lows = window.loc[window["is_pivot_low"], "zz_value"]

        price = df.iloc[-1]["Close"]

        if piv_highs.empty and piv_lows.empty:
            return Signal("NEUTRAL", 0.1, ["No swing points detected"])

        nearest_res = piv_highs[piv_highs > price].min() if (piv_highs > price).any() else None
        nearest_sup = piv_lows[piv_lows < price].max() if (piv_lows < price).any() else None

        reasons = []
        if nearest_res is not None:
            reasons.append(f"Resistance at {nearest_res:.5f}")
        if nearest_sup is not None:
            reasons.append(f"Support at {nearest_sup:.5f}")

        if nearest_res is not None:
            dist_res = abs(price - nearest_res) / price * 10000  # pips approx (4-digit)
            if dist_res < 15:
                return Signal("SELL", 0.55, reasons + ["Testing resistance (possible rejection)"])
        if nearest_sup is not None:
            dist_sup = abs(price - nearest_sup) / price * 10000
            if dist_sup < 15:
                return Signal("BUY", 0.55, reasons + ["Testing support (possible bounce)"])

        return Signal("NEUTRAL", 0.1, reasons + ["Price away from key levels"])


class IchimokuCloud(BaseStrategy):
    """
    Ichimoku Cloud strategy.

    Uses the classic 9/26/52/26 parameters:
      - Tenkan-sen (conversion) and Kijun-sen (base) crossovers
      - Price vs. cloud (Senkou A/B) for trend bias
      - Chikou span vs. price for confirmation
    """

    name = "Ichimoku Cloud"

    def __init__(
        self,
        tenkan: int = 9,
        kijun: int = 26,
        senkou_b: int = 52,
        displacement: int = 26,
    ):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b
        self.displacement = displacement

    def generate(self, df) -> Signal:
        required = ["ich_tenkan", "ich_kijun", "ich_senkou_a", "ich_senkou_b", "ich_chikou"]
        if not all(c in df for c in required):
            return Signal("NEUTRAL", 0.0, ["Missing Ichimoku columns"])

        import math

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last["Close"]

        tenkan = last["ich_tenkan"]
        kijun = last["ich_kijun"]
        senkou_a = last["ich_senkou_a"]
        senkou_b = last["ich_senkou_b"]
        chikou = last["ich_chikou"]

        # Chikou is close shifted -26 rows, so the last 26 rows are NaN.
        has_chikou = not (isinstance(chikou, float) and math.isnan(chikou))
        if not has_chikou:
            # Fall back: compare price vs. close 26 bars ago as a proxy.
            idx = len(df) - 1 - 26
            chikou = df.iloc[idx]["Close"] if idx >= 0 else price

        reasons = [
            f"Tenkan {tenkan:.5f}, Kijun {kijun:.5f}",
            f"Cloud {min(senkou_a, senkou_b):.5f}-{max(senkou_a, senkou_b):.5f}",
        ]

        # --- Trend bias via price vs cloud ---
        above_cloud = price > max(senkou_a, senkou_b)
        below_cloud = price < min(senkou_a, senkou_b)

        # --- Tenkan/Kijun cross ---
        cross_buy = prev["ich_tenkan"] <= prev["ich_kijun"] and tenkan > kijun
        cross_sell = prev["ich_tenkan"] >= prev["ich_kijun"] and tenkan < kijun

        # --- Chikou confirmation (price vs chikou 26 bars ago) ---
        chikou_bull = chikou > prev["Close"]
        chikou_bear = chikou < prev["Close"]

        if cross_buy and above_cloud and chikou_bull:
            return Signal(
                "BUY",
                0.8,
                reasons
                + [
                    "Bullish TK cross, price above cloud, chikou confirming",
                    f"Price {price:.5f} above cloud",
                ],
            )
        if cross_sell and below_cloud and chikou_bear:
            return Signal(
                "SELL",
                0.8,
                reasons
                + [
                    "Bearish TK cross, price below cloud, chikou confirming",
                    f"Price {price:.5f} below cloud",
                ],
            )

        # --- Weaker signals (fewer confirmations) ---
        if cross_buy and (above_cloud or chikou_bull):
            return Signal("BUY", 0.5, reasons + ["Bullish TK cross, partial confirmation"])
        if cross_sell and (below_cloud or chikou_bear):
            return Signal("SELL", 0.5, reasons + ["Bearish TK cross, partial confirmation"])

        if above_cloud and tenkan > kijun:
            return Signal("BUY", 0.4, reasons + ["Uptrend: price above cloud, TK bullish"])
        if below_cloud and tenkan < kijun:
            return Signal("SELL", 0.4, reasons + ["Downtrend: price below cloud, TK bearish"])

        return Signal("NEUTRAL", 0.1, reasons + ["No clear Ichimoku setup"])
