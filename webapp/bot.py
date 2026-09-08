"""
In-memory trading bot controller for the Bot tab.

The bot wraps the real Scanner engine: it keeps a per-strategy enabled flag
plus an overall run/stopped state, and exposes a "run" action that scans the
configured pair list and opens a paper trade on the strongest actionable
signal (BUY or SELL) that passes the confluence/min-score filter. Strategy
weights adapt after enough signal history, mirroring the reference app.

State is process-local (resets on Vercel cold start) — consistent with the
demo nature of the tab.
"""

import threading
import time
from typing import Dict, List, Optional

from scanner.engine import Scanner

# Bot strategies = the engine's real strategies (display names).
BOT_STRATEGIES = [
    "MA Crossover",
    "RSI Mean Reversion",
    "MACD",
    "Bollinger Bounce",
    "Stochastic",
    "Trend Continuation",
    "Support / Resistance",
    "Ichimoku Cloud",
]

# Default confluence weights per strategy (score 0-20 scale, 10 active).
DEFAULT_WEIGHTS: Dict[str, float] = {
    "MA Crossover": 2.0,
    "RSI Mean Reversion": 2.0,
    "MACD": 2.0,
    "Bollinger Bounce": 2.0,
    "Stochastic": 2.0,
    "Trend Continuation": 2.0,
    "Support / Resistance": 2.0,
    "Ichimoku Cloud": 2.0,
}


class BotController:
    """Tracks bot config + state and produces trades through a PaperTrader."""

    def __init__(self, trader):
        # RLock: methods like pause_strategy()/set_config() hold the lock while
        # calling self.state(), which re-acquires the same lock. A plain Lock
        # would self-deadlock, so a reentrant RLock is required here.
        self._lock = threading.RLock()
        self.trader = trader
        self.running = False
        self.enabled = {name: True for name in BOT_STRATEGIES}
        self.weights = dict(DEFAULT_WEIGHTS)
        self.signal_history: List[dict] = []
        self.last_run: Optional[dict] = None
        self.log: List[dict] = []
        self.min_score = 12.0
        self.pairs = [
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USDCHF",
            "AUDUSD",
            "USDCAD",
            "NZDUSD",
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _log(self, level: str, message: str) -> None:
        self.log.append(
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": level,
                "message": message,
            }
        )
        self.log = self.log[-100:]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def state(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "enabled": dict(self.enabled),
                "weights": dict(self.weights),
                "min_score": self.min_score,
                "pairs": list(self.pairs),
                "strategies": BOT_STRATEGIES,
                "signal_history": list(self.signal_history[-100:]),
                "last_run": self.last_run,
                "log": list(self.log),
            }

    def set_config(self, payload: dict) -> dict:
        with self._lock:
            if "enabled" in payload and isinstance(payload["enabled"], dict):
                for name, flag in payload["enabled"].items():
                    if name in self.enabled:
                        self.enabled[name] = bool(flag)
            if "min_score" in payload:
                try:
                    self.min_score = float(payload["min_score"])
                except (TypeError, ValueError):
                    pass
            if "pairs" in payload and isinstance(payload["pairs"], list):
                clean = [p.strip().upper() for p in payload["pairs"] if p.strip()]
                if clean:
                    self.pairs = clean
            self._log("info", "Configuration saved")
            return self.state()

    def reset(self) -> dict:
        with self._lock:
            self.enabled = {name: True for name in BOT_STRATEGIES}
            self.weights = dict(DEFAULT_WEIGHTS)
            self.signal_history = []
            self.min_score = 12.0
            self.last_run = None
            self.running = False
            self._log("info", "Bot reset to defaults")
            return self.state()

    def pause_strategy(self, name: str) -> dict:
        with self._lock:
            if name in self.enabled:
                self.enabled[name] = False
                self._log("info", f"Strategy paused: {name}")
            return self.state()

    def resume_strategy(self, name: str) -> dict:
        with self._lock:
            if name in self.enabled:
                self.enabled[name] = True
                self._log("info", f"Strategy resumed: {name}")
            return self.state()

    def close_trade(self, pos_id: str, price: float) -> dict:
        trade = self.trader.close_position(pos_id, price)
        if trade is not None:
            self._log(
                "info",
                f"Closed {trade['side']} {trade['pair']} @ {trade['close_price']} "
                f"PnL {trade['pnl']:+.2f} ({trade['pnl_pips']:+.1f} pips)",
            )
        return self.state()

    # ------------------------------------------------------------------
    # Bot run: scan pairs, score confluence, open best trade
    # ------------------------------------------------------------------
    def _confluence_score(self, result) -> float:
        """Weighted confluence score on a 0-20 scale from individual signals."""
        score = 0.0
        for sig in result.individual:
            name, signal = sig
            if signal.action == "NEUTRAL":
                continue
            weight = self.weights.get(name, 2.0)
            score += weight * (1.0 if signal.action == result.overall.action else -0.5)
        return round(max(0.0, min(20.0, score)), 2)

    def run(
        self,
        scanner: Scanner,
        data: Dict[str, object],
        price_fn,
        manual: bool = False,
    ) -> dict:
        """Scan pairs and open a paper trade on the best signal >= min_score."""
        with self._lock:
            active = [s.name for s in scanner.strategies if self.enabled.get(s.name, True)]
            if not active:
                self._log("warn", "No strategies enabled — nothing to trade")
                self.last_run = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trades": 0}
                return self.state()

            # Restrict the scanner to enabled strategies.
            scanner.strategies = [s for s in scanner.strategies if s.name in active]
            results = scanner.scan_many(data)

            best = None
            for r in results:
                if r.overall.action == "NEUTRAL":
                    continue
                score = self._confluence_score(r)
                self.signal_history.append(
                    {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "pair": r.pair, "action": r.overall.action, "score": score}
                )
                if score >= self.min_score and (best is None or score > best["score"]):
                    best = {"result": r, "score": score}

            opened = 0
            if best is not None:
                r = best["result"]
                price = price_fn(r.pair) or r.price
                side = r.overall.action
                self.trader.open_order(
                    pair=r.pair,
                    side=side,
                    units=10000,
                    open_price=price,
                    sl=r.stop_loss,
                    tp=r.take_profit,
                    label="bot",
                )
                opened = 1
                self._log(
                    "trade",
                    f"{side} {r.pair} @ {price:.5f} (score {best['score']}) "
                    f"SL {r.stop_loss} TP {r.take_profit}",
                )

            self.last_run = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "trades_opened": opened,
                "best_signal": (
                    {"pair": best["result"].pair, "action": best["result"].overall.action,
                     "score": best["score"], "price": best["result"].price}
                    if best else None
                ),
            }
            if not manual:
                self._log("info", "Bot scan cycle complete")
            return self.state()
