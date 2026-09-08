"""
OANDA-ready adapter.

Implements the same endpoint surface the reference app expects
(/api/oanda-account, /api/oanda-order, /api/oanda-close, /api/oanda-prices)
against our paper-trader store. When real OANDA v20 credentials are provided
via environment variables (OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENV), a real
integration could be dropped in here; until then every call is served from the
in-memory paper account so the tab is fully interactive with no API key.
"""

import os
import threading
from typing import Dict, List, Optional


class OandaAdapter:
    def __init__(self, trader):
        self._lock = threading.Lock()
        self.trader = trader
        self.env = os.environ.get("OANDA_ENV", "practice")
        self.connected = bool(
            os.environ.get("OANDA_API_KEY") and os.environ.get("OANDA_ACCOUNT_ID")
        )

    @property
    def mode(self) -> str:
        return "live" if self.connected else "paper"

    def status(self, prices: Optional[Dict[str, float]] = None) -> dict:
        account = self.trader.account(prices)
        return {
            "mode": self.mode,
            "env": self.env,
            "connected": self.connected,
            "account_id": os.environ.get("OANDA_ACCOUNT_ID"),
            "currency": "USD",
            **account,
        }

    def order(
        self,
        pair: str,
        side: str,
        units: float,
        open_price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict:
        if self.mode == "live":
            # Real OANDA v20 integration point.
            raise NotImplementedError("OANDA live trading not configured")
        return self.trader.open_order(
            pair=pair,
            side=side,
            units=units,
            open_price=open_price,
            sl=sl,
            tp=tp,
            label="oanda",
        )

    def close(self, pos_id: str, close_price: float) -> dict:
        if self.mode == "live":
            raise NotImplementedError("OANDA live trading not configured")
        trade = self.trader.close_position(pos_id, close_price)
        return {"closed": trade is not None, "trade": trade}

    def prices(self, pairs: List[str], price_fn) -> dict:
        quotes = {}
        for pair in pairs:
            price = price_fn(pair)
            if price is not None:
                spread = price * 0.0001  # simulated 1 pip spread
                quotes[pair] = {
                    "bid": round(price - spread / 2, 6),
                    "ask": round(price + spread / 2, 6),
                    "mid": round(price, 6),
                    "spread": round(spread, 6),
                }
        return {"mode": self.mode, "quotes": quotes}
