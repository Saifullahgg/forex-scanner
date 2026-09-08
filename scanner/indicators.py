"""
Technical indicator calculations for the Forex Signal Scanner.

All functions operate on pandas DataFrames containing OHLCV data
with columns: Open, High, Low, Close, Volume.
"""

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss == 0, RSI is 100 (all gains).
    rsi_val = rsi_val.fillna(100.0)
    return rsi_val


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    """
    MACD line, signal line and histogram.
    Returns a DataFrame with columns: macd, signal, hist.
    """
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Bollinger Bands.
    Returns a DataFrame with columns: upper, middle, lower, bandwidth, %b.
    """
    middle = sma(series, period)
    std = series.rolling(window=period).std(ddof=0)
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle
    percent_b = (series - lower) / (upper - lower)
    return pd.DataFrame(
        {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
        }
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def stochastic(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3, smooth: int = 3
):
    """
    Stochastic oscillator (%K and %D).
    """
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    raw_k = 100.0 * (df["Close"] - low_min) / (high_max - low_min)
    k = raw_k.rolling(window=smooth).mean()
    d = k.rolling(window=d_period).mean()
    return k, d


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder's)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_wilder = tr.ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100.0 * (
        pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()
        / atr_wilder
    )
    minus_di = 100.0 * (
        pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()
        / atr_wilder
    )

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val


def ichimoku(df: pd.DataFrame):
    """
    Ichimoku Cloud components.
    Returns DataFrame with columns: tenkan, kijun, senkou_a, senkou_b, chikou.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)

    return pd.DataFrame(
        {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "chikou": chikou,
        }
    )


def zigzag(df: pd.DataFrame, deviation_pct: float = 1.0):
    """
    Simple ZigZag swing points based on percentage deviation.
    Returns DataFrame with columns: zz_value, is_pivot_high, is_pivot_low.
    """
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    close = df["Close"].to_numpy()

    n = len(close)
    zz = np.full(n, np.nan)
    pivot_high = np.zeros(n, dtype=bool)
    pivot_low = np.zeros(n, dtype=bool)

    if n < 2:
        return pd.DataFrame(
            {
                "zz_value": zz,
                "is_pivot_high": pivot_high,
                "is_pivot_low": pivot_low,
            },
            index=df.index,
        )

    direction = 0  # 1 = up, -1 = down
    last_pivot_price = close[0]
    last_pivot_idx = 0
    last_pivot_kind = 0  # 1 = high, -1 = low

    for i in range(1, n):
        if direction >= 0:
            if high[i] > last_pivot_price:
                last_pivot_price = high[i]
                last_pivot_idx = i
                last_pivot_kind = 1
            elif low[i] < last_pivot_price * (1 - deviation_pct / 100.0):
                zz[last_pivot_idx] = last_pivot_price
                pivot_high[last_pivot_idx] = True
                direction = -1
                last_pivot_price = low[i]
                last_pivot_idx = i
                last_pivot_kind = -1
        if direction <= 0:
            if low[i] < last_pivot_price:
                last_pivot_price = low[i]
                last_pivot_idx = i
                last_pivot_kind = -1
            elif high[i] > last_pivot_price * (1 + deviation_pct / 100.0):
                zz[last_pivot_idx] = last_pivot_price
                pivot_low[last_pivot_idx] = True
                direction = 1
                last_pivot_price = high[i]
                last_pivot_idx = i
                last_pivot_kind = 1

    # Final leg
    if last_pivot_kind == 1:
        pivot_high[last_pivot_idx] = True
    elif last_pivot_kind == -1:
        pivot_low[last_pivot_idx] = True
    zz[last_pivot_idx] = last_pivot_price

    return pd.DataFrame(
        {
            "zz_value": zz,
            "is_pivot_high": pivot_high,
            "is_pivot_low": pivot_low,
        },
        index=df.index,
    )
