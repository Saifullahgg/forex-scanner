"""
Walk-forward backtester for the scanner engine.

Reuses the exact same indicator columns and strategy objects as the live
scanner (scanner.engine.Scanner), so backtest behaviour matches live signals.

Method: indicators are computed once on the full frame (every indicator in the
engine is backward-looking, so the value at row i only depends on rows <= i).
The bar index is then walked forward; at each bar the enabled strategies are
run against df.iloc[:i+1], exactly like scan_pair() does on the last bar.

A maximum of one open trade is kept at a time (like the live bot demo).
Entries trigger on the NEXT bar's open price to avoid look-ahead bias, and
trades exit on stop-loss / take-profit intrabar or at the final bar close.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .trading import pip_size


@dataclass
class BacktestTrade:
    pair: str
    side: str
    entry: float
    exit: float
    entry_time: str
    exit_time: str
    pnl_pips: float
    pnl_pct: float
    sl: float
    tp: float
    bars_held: int

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "side": self.side,
            "entry": round(self.entry, 6),
            "exit": round(self.exit, 6),
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "pnl_pips": round(self.pnl_pips, 1),
            "pnl_pct": round(self.pnl_pct, 2),
            "sl": round(self.sl, 6),
            "tp": round(self.tp, 6),
            "bars_held": self.bars_held,
        }


@dataclass
class BacktestResult:
    pair: str
    interval: str
    candles_used: int
    trades: List[BacktestTrade] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def equity_curve(self) -> List[dict]:
        """Cumulative PnL (in pips) after each trade."""
        curve: List[dict] = []
        cum = 0.0
        for t in self.trades:
            cum += t.pnl_pips
            curve.append({"exit_time": t.exit_time, "equity": round(cum, 1)})
        return curve

    @property
    def stats(self) -> dict:
        if not self.trades:
            return {
                "trades": 0,
                "win_rate": None,
                "avg_win_pips": None,
                "avg_loss_pips": None,
                "expected_value": None,
                "largest_win": None,
                "largest_loss": None,
                "total_pips": 0.0,
                "profit_factor": None,
            }
        wins = [t for t in self.trades if t.pnl_pips > 0]
        losses = [t for t in self.trades if t.pnl_pips <= 0]
        gross_win = sum(t.pnl_pips for t in wins)
        gross_loss = abs(sum(t.pnl_pips for t in losses))
        avg_win = gross_win / len(wins) if wins else 0.0
        avg_loss = gross_loss / len(losses) if losses else 0.0
        total = sum(t.pnl_pips for t in self.trades)

        return {
            "trades": len(self.trades),
            "win_rate": round(len(wins) / len(self.trades) * 100, 1),
            "avg_win_pips": round(avg_win, 1),
            "avg_loss_pips": round(avg_loss, 1),
            "expected_value": round((len(wins) * avg_win - len(losses) * avg_loss) / len(self.trades), 2),
            "largest_win": round(max(t.pnl_pips for t in self.trades), 1),
            "largest_loss": round(min(t.pnl_pips for t in self.trades), 1),
            "total_pips": round(total, 1),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        }

    @property
    def verdict(self) -> dict:
        """Verdict banner mirroring the reference app's thresholds."""
        s = self.stats
        if s["trades"] == 0:
            return {"label": "NO TRADES", "tone": "neutral", "detail": "No signals fired in this window"}
        wr = s["win_rate"]
        if wr >= 70:
            return {"label": "STRONG EDGE", "tone": "green", "detail": f"{wr}% win rate — high confidence edge"}
        if wr >= 55:
            return {"label": "MODEST EDGE", "tone": "blue", "detail": f"{wr}% win rate — usable but thin"}
        if wr >= 45:
            return {"label": "NO EDGE", "tone": "gold", "detail": f"{wr}% win rate — roughly breakeven"}
        return {"label": "AVOID", "tone": "red", "detail": f"{wr}% win rate — losing edge"}

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "candles_used": self.candles_used,
            "stats": self.stats,
            "verdict": self.verdict,
            "equity_curve": self.equity_curve,
            "trades": [t.to_dict() for t in self.trades],
        }


def _aggregate(scanner, clean: pd.DataFrame):
    """Mirror scan_pair's weighted aggregation for a slice."""
    price = float(clean.iloc[-1]["Close"])
    buy_strength, sell_strength = 0.0, 0.0
    buy_count, sell_count = 0, 0
    for strat in scanner.strategies:
        try:
            sig = strat.generate(clean)
        except Exception:  # noqa: BLE001
            continue
        if sig.action == "BUY":
            buy_strength += sig.strength
            buy_count += 1
        elif sig.action == "SELL":
            sell_strength += sig.strength
            sell_count += 1

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

    if action == "BUY" and buy_count < 2:
        action = "NEUTRAL"
    elif action == "SELL" and sell_count < 2:
        action = "NEUTRAL"
    return action, price


def run_backtest(
    df: pd.DataFrame,
    scanner,
    pair: str,
    interval: str,
    max_candles: int = 5000,
) -> BacktestResult:
    """Replay the strategy set over historical candles."""
    if df is None or len(df) < 60:
        raise ValueError("Insufficient data to backtest")

    full = scanner.compute_indicators(df)
    full = full.dropna(
        subset=[
            f"ema_{scanner.ema_fast}",
            f"ema_{scanner.ema_slow}",
            f"rsi_{scanner.rsi_period}",
            f"adx_{scanner.adx_period}",
        ]
    ).reset_index(drop=True)

    if len(full) < 60:
        raise ValueError("Not enough clean data after indicator warm-up")

    work = full.tail(max_candles).reset_index(drop=True)
    if len(work) < 60:
        raise ValueError("Not enough candles for requested replay window")

    atr_col = "atr_14"
    trades: List[BacktestTrade] = []
    open_pos = None  # dict: side, entry, entry_time, sl, tp, entry_idx

    n = len(work)
    for i in range(60, n):
        # ----- Exit an open trade using this bar's high/low/close -----
        if open_pos is not None:
            bar = work.iloc[i]
            hit, exit_price, reason = None, None, None
            if open_pos["side"] == "BUY":
                if bar["Low"] <= open_pos["sl"]:
                    hit, exit_price = "SL", open_pos["sl"]
                elif bar["High"] >= open_pos["tp"]:
                    hit, exit_price = "TP", open_pos["tp"]
            else:
                if bar["High"] >= open_pos["sl"]:
                    hit, exit_price = "SL", open_pos["sl"]
                elif bar["Low"] <= open_pos["tp"]:
                    hit, exit_price = "TP", open_pos["tp"]

            if hit is None:
                # Exit at close if the signal reverses hard or at the last bar.
                if i == n - 1:
                    hit, exit_price = "CLOSE", float(bar["Close"])
                else:
                    close = float(bar["Close"])
                    if open_pos["side"] == "BUY" and close < open_pos["entry"] * 0.995:
                        hit, exit_price = "EXIT", close
                    elif open_pos["side"] == "SELL" and close > open_pos["entry"] * 1.005:
                        hit, exit_price = "EXIT", close

            if hit is not None:
                side = open_pos["side"]
                direction = 1 if side == "BUY" else -1
                pnl_pips = direction * (exit_price - open_pos["entry"]) / pip_size(open_pos["entry"])
                pnl_pct = direction * (exit_price / open_pos["entry"] - 1) * 100
                trades.append(
                    BacktestTrade(
                        pair=pair,
                        side=side,
                        entry=open_pos["entry"],
                        exit=exit_price,
                        entry_time=open_pos["entry_time"],
                        exit_time=str(work.index[i]),
                        pnl_pips=pnl_pips,
                        pnl_pct=pnl_pct,
                        sl=open_pos["sl"],
                        tp=open_pos["tp"],
                        bars_held=i - open_pos["entry_idx"],
                    )
                )
                open_pos = None

        # ----- Signal at current bar -> enter on NEXT bar open -----
        if open_pos is None and i < n - 1:
            action, _ = _aggregate(scanner, work.iloc[: i + 1])
            if action in ("BUY", "SELL"):
                bar = work.iloc[i]
                atr_val = float(bar[atr_col])
                entry = float(work.iloc[i + 1]["Open"])
                if action == "BUY":
                    sl = entry - scanner.sl_atr_mult * atr_val
                    tp = entry + scanner.tp_atr_mult * atr_val
                else:
                    sl = entry + scanner.sl_atr_mult * atr_val
                    tp = entry - scanner.tp_atr_mult * atr_val
                open_pos = {
                    "side": action,
                    "entry": entry,
                    "entry_time": str(work.index[i]),
                    "entry_idx": i + 1,
                    "sl": sl,
                    "tp": tp,
                }

    return BacktestResult(
        pair=pair,
        interval=interval,
        candles_used=len(work),
        trades=trades,
    )
