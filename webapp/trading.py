"""
In-memory paper trading store shared by the Demo and OANDA tabs.

Positions are marked to market against the latest fetched price from the
data provider (falling back to the entry price when no feed is available).

NOTE: State is process-local. On Vercel serverless, the store resets on cold
start. This matches the "paper trading demo" experience and requires no API
key. Real OANDA v20 integration can be layered on later via environment keys.
"""

import threading
import time
from typing import Dict, List, Optional


def pip_size(price: float) -> float:
    """Approximate pip size: 0.01 for JPY-quoted pairs, 0.0001 otherwise."""
    return 0.01 if price >= 50 else 0.0001


# Standard forex lot sizes expressed in base-currency units.
#   micro lot = 1,000 units, mini lot = 10,000 units, standard lot = 100,000 units.
LOT_SIZES = {
    "micro": 1_000,
    "mini": 10_000,
    "standard": 100_000,
}

# The quick "Take Demo Trade" flow expresses size in standard lots and the
# user's account leverage (e.g. 1:100). Margin is then notional / leverage,
# matching how the reference app presents the trade before execution.
DEFAULT_LEVERAGE = 100.0
DEFAULT_UNITS = 10_000.0


def lots_to_units(lots: float, lot_size: str = "standard") -> float:
    """Convert a number of lots into base-currency units.

    Uses the conventional 1 standard lot = 100,000 units. Fractional lots are
    supported (0.1 = 10,000 units, 0.01 = 1,000 units). Raises ValueError for
    non-positive sizes.
    """
    lots = float(lots)
    if lots <= 0:
        raise ValueError("lots must be positive")
    return lots * LOT_SIZES.get(lot_size, LOT_SIZES["standard"])


class PaperTrader:
    """A tiny in-memory futures-style paper trading account."""

    def __init__(self, starting_balance: float = 100_000.0):
        self._lock = threading.Lock()
        self.starting_balance = float(starting_balance)
        self.reset()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            self.balance = self.starting_balance
            self.positions: Dict[str, dict] = {}
            self.closed: List[dict] = []
            self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"T{self._seq:04d}"

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ------------------------------------------------------------------
    # Pricing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _pnl(pos: dict, mark: float) -> float:
        direction = 1 if pos["side"] == "BUY" else -1
        return direction * (mark - pos["open_price"]) * pos["units"]

    @staticmethod
    def _pips(pos: dict, exit_price: float) -> float:
        direction = 1 if pos["side"] == "BUY" else -1
        return round(
            direction * (exit_price - pos["open_price"]) / pip_size(pos["open_price"]), 1
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def account(self, prices: Optional[Dict[str, float]] = None) -> dict:
        """Account snapshot with open positions marked to market."""
        prices = prices or {}
        with self._lock:
            open_positions: List[dict] = []
            unrealized = 0.0
            for pos in self.positions.values():
                mark = prices.get(pos["pair"], pos["open_price"])
                pnl = self._pnl(pos, mark)
                unrealized += pnl
                open_positions.append(
                    {
                        **pos,
                        "current_price": round(mark, 6),
                        "unrealized_pnl": round(pnl, 2),
                    }
                )

            wins = sum(1 for t in self.closed if t["pnl"] > 0)
            losses = sum(1 for t in self.closed if t["pnl"] < 0)
            total_pnl = sum(t["pnl"] for t in self.closed)

            return {
                "mode": "paper",
                "balance": round(self.balance, 2),
                "equity": round(self.balance + unrealized, 2),
                "unrealized_pnl": round(unrealized, 2),
                "margin_used": round(sum(p["margin"] for p in self.positions.values()), 2),
                "starting_balance": self.starting_balance,
                "open_positions": open_positions,
                "open_count": len(open_positions),
                "closed_count": len(self.closed),
                "win_rate": round(wins / len(self.closed) * 100, 1) if self.closed else None,
                "total_pnl": round(total_pnl, 2),
                "history": list(reversed(self.closed[-200:])),
            }

    def open_order(
        self,
        pair: str,
        side: str,
        units: float,
        open_price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        label: str = "demo",
        leverage: Optional[float] = None,
    ) -> dict:
        with self._lock:
            side = side.upper()
            if side not in ("BUY", "SELL"):
                raise ValueError("side must be BUY or SELL")
            if units <= 0:
                raise ValueError("units must be positive")
            if leverage is not None:
                leverage = float(leverage)
                if leverage <= 0:
                    raise ValueError("leverage must be positive")
                margin = abs(units) * open_price / leverage
            else:
                margin = abs(units) * open_price  # simple notional margin
            pos = {
                "id": self._next_id(),
                "pair": pair,
                "side": side,
                "units": round(units, 4),
                "open_price": round(open_price, 6),
                "sl": round(sl, 6) if sl is not None else None,
                "tp": round(tp, 6) if tp is not None else None,
                "open_time": self._now(),
                "label": label,
                "leverage": round(leverage, 2) if leverage else None,
                "margin": round(margin, 2),
            }
            self.positions[pos["id"]] = pos
            return {**pos, "current_price": open_price, "unrealized_pnl": 0.0}

    def close_position(self, pos_id: str, close_price: float) -> Optional[dict]:
        with self._lock:
            pos = self.positions.pop(pos_id, None)
            if pos is None:
                return None
            pnl = self._pnl(pos, close_price)
            self.balance += pnl
            trade = {
                **pos,
                "close_price": round(close_price, 6),
                "close_time": self._now(),
                "pnl": round(pnl, 2),
                "pnl_pips": self._pips(pos, close_price),
            }
            self.closed.append(trade)
            return trade

    def close_all(self, price_fn) -> int:
        """Close every open position using the given price lookup."""
        closed = 0
        for pos_id in list(self.positions.keys()):
            price = price_fn(self.positions[pos_id]["pair"])
            if price is not None and self.close_position(pos_id, price) is not None:
                closed += 1
        return closed

    # ------------------------------------------------------------------
    # Monthly assessment grid used by the OANDA-style tab
    # ------------------------------------------------------------------
    def monthly_summary(self) -> dict:
        """Group closed trades by YYYY-MM with win/loss/PnL counts."""
        with self._lock:
            months: Dict[str, dict] = {}
            for t in self.closed:
                key = t["close_time"][:7]  # YYYY-MM
                bucket = months.setdefault(
                    key, {"trades": 0, "wins": 0, "losses": 0, "net": 0.0}
                )
                bucket["trades"] += 1
                bucket["net"] = round(bucket["net"] + t["pnl"], 2)
                if t["pnl"] > 0:
                    bucket["wins"] += 1
                elif t["pnl"] < 0:
                    bucket["losses"] += 1
            rows = []
            for key in sorted(months, reverse=True):
                b = months[key]
                rows.append(
                    {
                        "month": key,
                        "trades": b["trades"],
                        "wins": b["wins"],
                        "losses": b["losses"],
                        "win_rate": round(b["wins"] / b["trades"] * 100, 1)
                        if b["trades"]
                        else None,
                        "net_pnl": b["net"],
                    }
                )
            return {"months": rows}
