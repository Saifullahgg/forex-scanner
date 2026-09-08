"""
Data provider for the Forex Signal Scanner.

Uses yfinance to fetch free forex OHLCV data.
Note: yfinance forex symbols use the format "EURUSD=X".
"""

import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Common major and cross currency pairs
MAJOR_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
]

CROSS_PAIRS = [
    "EURGBP",
    "EURJPY",
    "EURCHF",
    "EURCAD",
    "EURAUD",
    "EURNZD",
    "GBPJPY",
    "GBPCHF",
    "GBPCAD",
    "GBPAUD",
    "GBPNZD",
    "CHFJPY",
    "CADJPY",
    "AUDJPY",
    "NZDJPY",
    "AUDCAD",
    "AUDCHF",
    "AUDNZD",
    "NZDCHF",
    "NZDCAD",
    "CADCHF",
]

EXOTIC_PAIRS = [
    "USDTRY",
    "USDZAR",
    "USDINR",
    "USDMXN",
    "USDPLN",
    "USDDKK",
    "USDSGD",
    "USDHKD",
]

ALL_PAIRS = MAJOR_PAIRS + CROSS_PAIRS + EXOTIC_PAIRS


def to_yahoo_symbol(pair: str) -> str:
    """Convert 'EURUSD' to 'EURUSD=X'."""
    return f"{pair}=X"


def from_yahoo_symbol(symbol: str) -> str:
    """Convert 'EURUSD=X' back to 'EURUSD'."""
    return symbol.replace("=X", "")


def fetch_data(
    pair: str,
    interval: str = "1h",
    period: str = "1mo",
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a forex pair.

    Args:
        pair: e.g. "EURUSD"
        interval: "1m", "5m", "15m", "30m", "1h", "4h", "1d"
        period: "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"
        retries: number of attempts before giving up

    Returns:
        DataFrame with columns Open, High, Low, Close, Volume
        or None on failure.
    """
    symbol = to_yahoo_symbol(pair)
    import yfinance as yf

    for attempt in range(1, retries + 1):
        try:
            df = yf.download(
                symbol,
                interval=interval,
                period=period,
                progress=False,
                auto_adjust=False,
            )
            if df is None or df.empty:
                print(f"  [warn] {pair}: no data returned")
                return None

            df = df.rename(columns=str.strip)
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df) < 60:
                print(f"  [warn] {pair}: only {len(df)} candles, need >= 60")
                return None
            return df
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {pair}: attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(1.5 * attempt)
    return None


def fetch_many(
    pairs: List[str],
    interval: str = "1h",
    period: str = "1mo",
    delay: float = 0.5,
) -> Dict[str, Optional[pd.DataFrame]]:
    """Fetch data for several pairs, returning {pair: DataFrame}."""
    results: Dict[str, Optional[pd.DataFrame]] = {}
    for pair in pairs:
        results[pair] = fetch_data(pair, interval=interval, period=period)
        if delay:
            time.sleep(delay)
    return results
