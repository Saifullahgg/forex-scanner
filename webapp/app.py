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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

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

from .cache import TTLCache

app = FastAPI(title="Forex Scanner Web", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"

# In-memory TTL cache to respect Yahoo Finance rate limits.
data_cache = TTLCache(ttl=300.0)
_cache_lock = threading.Lock()

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

    data: Dict[str, Optional[pd.DataFrame]] = {}
    for pair in pair_list:
        data[pair] = _cached_fetch(pair, interval=interval, period=period)

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
