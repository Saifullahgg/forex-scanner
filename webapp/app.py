"""
FastAPI web interface for the Forex Signal Scanner.

Wraps the existing CLI engine (scanner.engine.Scanner) and data provider
(scanner.data_provider) as a reusable library. The API payload for /api/scan
is exactly ScanResult.to_dict(), the same shape as the CLI's --json output.

Run with:

    python run_web.py
    uvicorn webapp.app:app --reload
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scanner.data_provider import (
    ALL_PAIRS,
    CROSS_PAIRS,
    EXOTIC_PAIRS,
    MAJOR_PAIRS,
    fetch_data,
)
from scanner.engine import Scanner

from .backtest import run_backtest
from .bot import BotController
from .cache import TTLCache
from .market import market_clock, rolling_calendar
from .oanda import OandaAdapter
from .trading import (
    DEFAULT_LEVERAGE,
    DEFAULT_UNITS,
    LOT_SIZES,
    PaperTrader,
    lots_to_units,
    pip_size,
)

app = FastAPI(title="Forex Scanner Web", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"

# In-memory TTL cache to respect Yahoo Finance rate limits.
data_cache = TTLCache(ttl=300.0)
# Short-lived cache so live marking uses near-real-time 1-minute closes.
live_cache = TTLCache(ttl=15.0)
_cache_lock = threading.Lock()

# Shared paper-trading / bot / OANDA state (process-local, demo-grade).
trader = PaperTrader(starting_balance=100_000.0)
oanda_adapter = OandaAdapter(trader)
bot_controller = BotController(trader)


def _latest_price(pair: str) -> Optional[float]:
    """Best-effort latest close for marking paper positions to market."""
    df = _cached_fetch(pair, interval="15m", period="5d")
    if df is None or df.empty:
        return None
    return float(df.iloc[-1]["Close"])


def _fetch_live(pair: str) -> Optional[pd.DataFrame]:
    """Fetch 1-minute candles with a short (15s) TTL for live marking."""
    key = (pair, "1m", "1d")
    with _cache_lock:
        cached = live_cache.get(key)
        if cached is not None:
            return cached
    df = fetch_data(pair, interval="1m", period="1d")
    if df is not None and not df.empty:
        with _cache_lock:
            live_cache.set(key, df)
    return df


def _live_price(pair: str) -> Optional[float]:
    """Best-effort live price; falls back to the 15m close when 1m is unavailable."""
    df = _fetch_live(pair)
    if df is not None and not df.empty:
        return float(df.iloc[-1]["Close"])
    return _latest_price(pair)

VALID_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
VALID_PERIODS = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]

# Strategy names are derived from the engine itself so they always stay in
# sync with scanner/strategies.py.
_default_scanner = Scanner()
ALL_STRATEGIES = [s.name for s in _default_scanner.strategies]

# Config keys the /api/scan endpoint accepts as query parameters.
CONFIG_KEYS = [
    "ema_fast",
    "ema_slow",
    "rsi_period",
    "macd_fast",
    "macd_slow",
    "macd_signal",
    "bb_period",
    "bb_std",
    "stoch_k",
    "stoch_d",
    "adx_period",
    "adx_threshold",
    "zz_deviation",
    "sl_atr_mult",
    "tp_atr_mult",
]


def _normalize_pairs(raw: str) -> List[str]:
    """Split and validate a comma-separated pair list."""
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="No pairs provided")
    for p in parts:
        if not (len(p) == 6 and p.isalpha()):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pair format: '{p}' (expected 6 letters, e.g. EURUSD)",
            )
    return list(dict.fromkeys(parts))


def _validate_enum(value: str, allowed: List[str], name: str) -> str:
    if value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {name} '{value}'. Allowed: {', '.join(allowed)}",
        )
    return value


def _cached_fetch(pair: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV with a TTL cache keyed by (pair, interval, period)."""
    key = (pair, interval, period)
    with _cache_lock:
        cached = data_cache.get(key)
        if cached is not None:
            return cached
    df = fetch_data(pair, interval=interval, period=period)
    if df is not None:
        with _cache_lock:
            data_cache.set(key, df)
    return df


def _fetch_many_parallel(
    pairs: List[str], interval: str, period: str, max_workers: int = 5
) -> Dict[str, Optional[pd.DataFrame]]:
    """Fetch OHLCV for many pairs concurrently.

    The serial per-pair loop makes full scans (36 pairs) take 30-60s and trips
    Yahoo rate limits, which makes the scanner tab appear broken. Fetching with
    a small thread pool cuts this to a few seconds while still respecting the
    TTL cache (each worker goes through _cached_fetch).
    """
    if not pairs:
        return {}
    if len(pairs) == 1:
        return {pairs[0]: _cached_fetch(pairs[0], interval=interval, period=period)}

    def _one(pair: str) -> Tuple[str, Optional[pd.DataFrame]]:
        return pair, _cached_fetch(pair, interval=interval, period=period)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_one, pairs))
        return dict(results)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] parallel fetch failed ({exc}); falling back to serial")
        return {p: _cached_fetch(p, interval=interval, period=period) for p in pairs}


@app.get("/")
def index() -> FileResponse:
    """Serve the dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": app.title,
        "version": app.version,
        "strategies": ALL_STRATEGIES,
        "cache_ttl_seconds": data_cache.ttl,
    }


@app.get("/api/pairs")
def pairs() -> dict:
    return {
        "major": MAJOR_PAIRS,
        "cross": CROSS_PAIRS,
        "exotic": EXOTIC_PAIRS,
        "all": ALL_PAIRS,
    }


@app.get("/api/scan")
def scan(
    pairs: str = Query(..., description="Comma-separated pair codes, e.g. EURUSD,GBPUSD"),
    interval: str = Query("1h", description="Candle interval"),
    period: str = Query("1mo", description="Look-back period"),
    strategies: Optional[str] = Query(
        None, description="Comma-separated strategy names to enable (default: all)"
    ),
    ema_fast: Optional[int] = None,
    ema_slow: Optional[int] = None,
    rsi_period: Optional[int] = None,
    macd_fast: Optional[int] = None,
    macd_slow: Optional[int] = None,
    macd_signal: Optional[int] = None,
    bb_period: Optional[int] = None,
    bb_std: Optional[float] = None,
    stoch_k: Optional[int] = None,
    stoch_d: Optional[int] = None,
    adx_period: Optional[int] = None,
    adx_threshold: Optional[float] = None,
    zz_deviation: Optional[float] = None,
    sl_atr_mult: Optional[float] = None,
    tp_atr_mult: Optional[float] = None,
) -> dict:
    interval = _validate_enum(interval, VALID_INTERVALS, "interval")
    period = _validate_enum(period, VALID_PERIODS, "period")
    pair_list = _normalize_pairs(pairs)

    config: Dict[str, object] = {}
    for key in CONFIG_KEYS:
        value = locals().get(key)
        if value is not None:
            config[key] = value

    scanner = Scanner(config)

    if strategies is not None:
        wanted = {s.strip() for s in strategies.split(",") if s.strip()}
        if not wanted:
            raise HTTPException(status_code=400, detail="No strategies selected")
        valid_names = {s.name for s in scanner.strategies}
        unknown = wanted - valid_names
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategies: {', '.join(sorted(unknown))}",
            )
        scanner.strategies = [s for s in scanner.strategies if s.name in wanted]

    data = _fetch_many_parallel(pair_list, interval=interval, period=period)

    results = scanner.scan_many(data)
    scanned_pairs = {r.pair for r in results}
    failed = [p for p in pair_list if p not in scanned_pairs]

    return {
        "interval": interval,
        "period": period,
        "strategies": [s.name for s in scanner.strategies],
        "config": config,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "failed": failed,
        "results": [r.to_dict() for r in results],
    }


def _clean_series(series: pd.Series) -> List[Optional[float]]:
    """Convert a pandas series to a JSON-safe list (NaN -> None)."""
    out: List[Optional[float]] = []
    for value in series:
        try:
            if pd.isna(value):
                out.append(None)
            else:
                out.append(round(float(value), 8))
        except (TypeError, ValueError):
            out.append(None)
    return out


@app.get("/api/pair/{pair}/chart")
def pair_chart(
    pair: str,
    interval: str = Query("1h"),
    period: str = Query("1mo"),
    limit: int = Query(200, ge=10, le=2000),
) -> dict:
    interval = _validate_enum(interval, VALID_INTERVALS, "interval")
    period = _validate_enum(period, VALID_PERIODS, "period")
    pair = _normalize_pairs(pair)[0]

    df = _cached_fetch(pair, interval=interval, period=period)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No data available for {pair}")

    scanner = Scanner()
    full = scanner.compute_indicators(df)
    last = full.tail(limit)

    times = [str(ts) for ts in last.index]

    indicators: Dict[str, List[Optional[float]]] = {}
    for col in last.columns:
        if col in ("Open", "High", "Low", "Close", "Volume"):
            continue
        indicators[col] = _clean_series(last[col])

    return {
        "pair": pair,
        "interval": interval,
        "period": period,
        "ohlcv": {
            "time": times,
            "open": _clean_series(last["Open"]),
            "high": _clean_series(last["High"]),
            "low": _clean_series(last["Low"]),
            "close": _clean_series(last["Close"]),
            "volume": _clean_series(last["Volume"]),
        },
        "indicators": indicators,
    }


# ======================================================================
# Tabbed SPA endpoints: Demo / OANDA / Bot / Backtest / Clock
# ======================================================================


# ------------------------------ Demo trading ------------------------------
@app.get("/api/demo/account")
def demo_account() -> dict:
    prices = {pos["pair"]: _live_price(pos["pair"]) for pos in trader.positions.values()}
    trader.mark_prices(prices)
    acc = trader.account(prices)
    acc["live_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return acc


@app.get("/api/demo/positions")
def demo_positions() -> dict:
    return {"positions": trader.account()["open_positions"]}


@app.post("/api/demo/order")
def demo_order(payload: dict) -> dict:
    pair = str(payload.get("pair", "")).upper()
    if not (len(pair) == 6 and pair.isalpha()):
        raise HTTPException(status_code=400, detail="Invalid pair format")
    side = str(payload.get("side", "BUY")).upper()
    price = float(payload.get("price") or 0) or (_live_price(pair) or 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Could not resolve a price")
    try:
        if payload.get("lots") is not None:
            units = lots_to_units(payload.get("lots"))
        else:
            units = float(payload.get("units", DEFAULT_UNITS))
        leverage = float(payload["leverage"]) if payload.get("leverage") else None
        pos = trader.open_order(
            pair=pair,
            side=side,
            units=units,
            open_price=price,
            sl=float(payload["sl"]) if payload.get("sl") else None,
            tp=float(payload["tp"]) if payload.get("tp") else None,
            label="demo",
            leverage=leverage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return pos


@app.post("/api/demo/margin")
def demo_margin(payload: dict) -> dict:
    """Quick trade preview used by the "Take Demo Trade" flow.

    Returns units, notional, margin (with leverage) and a conservative SL/TP
    risk preview so the UI can show the trade before executing it.
    """
    pair = str(payload.get("pair", "")).upper()
    if not (len(pair) == 6 and pair.isalpha()):
        raise HTTPException(status_code=400, detail="Invalid pair format")
    price = float(payload.get("price") or 0) or (_live_price(pair) or 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Could not resolve a price")
    try:
        if payload.get("lots") is not None:
            units = lots_to_units(payload.get("lots"))
        else:
            units = float(payload.get("units", DEFAULT_UNITS))
        leverage = float(payload.get("leverage") or DEFAULT_LEVERAGE)
        if leverage <= 0:
            raise ValueError("leverage must be positive")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    notional = units * price
    margin = notional / leverage
    sl = float(payload["sl"]) if payload.get("sl") else None
    tp = float(payload["tp"]) if payload.get("tp") else None
    side = str(payload.get("side", "BUY")).upper()
    direction = 1 if side == "BUY" else -1

    def risk(level):
        if level is None:
            return None
        return round(direction * (level - price) * units, 2)

    return {
        "pair": pair,
        "side": side,
        "units": round(units, 4),
        "lots": round(units / LOT_SIZES["standard"], 4),
        "price": round(price, 6),
        "notional": round(notional, 2),
        "margin": round(margin, 2),
        "leverage": round(leverage, 2),
        "pip_size": pip_size(price),
        "sl": sl,
        "tp": tp,
        "sl_risk": risk(sl),
        "tp_reward": risk(tp),
    }


@app.post("/api/demo/close")
def demo_close(payload: dict) -> dict:
    pos_id = str(payload.get("id", ""))
    price = float(payload.get("price") or 0)
    if not pos_id:
        raise HTTPException(status_code=400, detail="Missing position id")
    if price <= 0:
        pair = next((p["pair"] for p in trader.positions.values() if p["id"] == pos_id), None)
        price = _live_price(pair) if pair else None
        if price is None:
            raise HTTPException(status_code=400, detail="Could not resolve close price")
    trade = trader.close_position(pos_id, price)
    if trade is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return trade


@app.post("/api/demo/reset")
def demo_reset() -> dict:
    trader.reset()
    return {"status": "ok", "balance": trader.balance}


@app.get("/api/demo/monthly")
def demo_monthly() -> dict:
    return trader.monthly_summary()


# ------------------------------ OANDA-ready ------------------------------
@app.get("/api/oanda-account")
def oanda_account() -> dict:
    prices = {pos["pair"]: _latest_price(pos["pair"]) for pos in trader.positions.values()}
    return oanda_adapter.status(prices)


@app.post("/api/oanda-order")
def oanda_order(payload: dict) -> dict:
    pair = str(payload.get("pair", "")).upper()
    side = str(payload.get("side", "BUY")).upper()
    units = float(payload.get("units", 10000))
    price = float(payload.get("price") or 0) or (_latest_price(pair) or 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Could not resolve a price")
    try:
        return oanda_adapter.order(
            pair=pair,
            side=side,
            units=units,
            open_price=price,
            sl=float(payload["sl"]) if payload.get("sl") else None,
            tp=float(payload["tp"]) if payload.get("tp") else None,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@app.post("/api/oanda-close")
def oanda_close(payload: dict) -> dict:
    pos_id = str(payload.get("id", ""))
    price = float(payload.get("price") or 0)
    if not pos_id:
        raise HTTPException(status_code=400, detail="Missing position id")
    if price <= 0:
        pair = next((p["pair"] for p in trader.positions.values() if p["id"] == pos_id), None)
        price = _latest_price(pair) if pair else None
        if price is None:
            raise HTTPException(status_code=400, detail="Could not resolve close price")
    return oanda_adapter.close(pos_id, price)


@app.get("/api/oanda-prices")
def oanda_prices(pairs: str = Query("EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD")) -> dict:
    pair_list = _normalize_pairs(pairs)
    return oanda_adapter.prices(pair_list, _latest_price)


# ------------------------------ Bot control ------------------------------
@app.get("/api/bot-state")
def bot_state() -> dict:
    return bot_controller.state()


@app.post("/api/bot-state")
def bot_state_update(payload: dict) -> dict:
    action = payload.get("action", "")
    if action == "save_config":
        return bot_controller.set_config(payload)
    if action == "reset":
        return bot_controller.reset()
    if action == "pause_strategy":
        return bot_controller.pause_strategy(str(payload.get("strategy", "")))
    if action == "resume_strategy":
        return bot_controller.resume_strategy(str(payload.get("strategy", "")))
    if action == "close_trade":
        pos_id = str(payload.get("id", ""))
        price = float(payload.get("price") or 0)
        if price <= 0:
            pair = next((p["pair"] for p in trader.positions.values() if p["id"] == pos_id), None)
            price = _latest_price(pair) if pair else None
            if price is None:
                raise HTTPException(status_code=400, detail="Could not resolve close price")
        return bot_controller.close_trade(pos_id, price)
    raise HTTPException(status_code=400, detail=f"Unknown bot action: {action}")


@app.post("/api/bot-run")
def bot_run(payload: dict) -> dict:
    """Run a scan cycle and open a paper trade on the best confluence signal."""
    interval = _validate_enum(str(payload.get("interval", "1h")), VALID_INTERVALS, "interval")
    period = _validate_enum(str(payload.get("period", "1mo")), VALID_PERIODS, "period")
    scanner = Scanner({k: v for k, v in payload.items() if k in CONFIG_KEYS and v is not None})
    data = _fetch_many_parallel(bot_controller.pairs, interval=interval, period=period)
    return bot_controller.run(scanner, data, _latest_price, manual=True)


# ------------------------------ Backtest ------------------------------
@app.get("/api/backtest")
def backtest(
    pair: str = Query("EURUSD"),
    interval: str = Query("1h"),
    period: str = Query("6mo"),
    max_candles: int = Query(2000, ge=100, le=5000),
    ema_fast: Optional[int] = None,
    ema_slow: Optional[int] = None,
    rsi_period: Optional[int] = None,
    macd_fast: Optional[int] = None,
    macd_slow: Optional[int] = None,
    macd_signal: Optional[int] = None,
    bb_period: Optional[int] = None,
    bb_std: Optional[float] = None,
    stoch_k: Optional[int] = None,
    stoch_d: Optional[int] = None,
    adx_period: Optional[int] = None,
    adx_threshold: Optional[float] = None,
    zz_deviation: Optional[float] = None,
    sl_atr_mult: Optional[float] = None,
    tp_atr_mult: Optional[float] = None,
) -> dict:
    interval = _validate_enum(interval, VALID_INTERVALS, "interval")
    period = _validate_enum(period, VALID_PERIODS, "period")
    pair = _normalize_pairs(pair)[0]

    df = _cached_fetch(pair, interval=interval, period=period)
    if df is None:
        raise HTTPException(status_code=404, detail=f"No data available for {pair}")

    config: Dict[str, object] = {}
    for key in CONFIG_KEYS:
        value = locals().get(key)
        if value is not None:
            config[key] = value

    scanner = Scanner(config)
    try:
        result = run_backtest(df, scanner, pair=pair, interval=interval, max_candles=max_candles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result.to_dict()


# ------------------------------ Market clock / calendar ------------------------------
@app.get("/api/clock")
def clock() -> dict:
    return market_clock()


@app.get("/api/calendar")
def calendar(days: int = Query(7, ge=1, le=30)) -> dict:
    return {"events": rolling_calendar(days=days)}
