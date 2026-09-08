"""Shared fixtures for the forex-scanner test suite."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure the project root is importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_ohlcv(n: int = 300, base: float = 1.08, seed: int = 42) -> pd.DataFrame:
    """Generate a deterministic synthetic OHLCV DataFrame."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="h")

    drift = 0.0002
    returns = rng.normal(drift, 0.0015, n)
    closes = base * np.exp(np.cumsum(returns))

    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.0004, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.0004, n)))
    volumes = rng.integers(500, 5000, n).astype(float)

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


@pytest.fixture
def ohlcv():
    """Standard synthetic OHLCV fixture."""
    return make_ohlcv()


@pytest.fixture
def ohlcv_trending_up():
    """Steadily rising prices to force bullish strategies."""
    rng = np.random.default_rng(7)
    n = 300
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    closes = 1.05 * np.exp(np.cumsum(rng.normal(0.002, 0.001, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.001
    lows = np.minimum(opens, closes) * 0.999
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes,
         "Volume": rng.integers(500, 5000, n).astype(float)},
        index=dates,
    )


@pytest.fixture
def ohlcv_trending_down():
    """Steadily falling prices to force bearish strategies."""
    rng = np.random.default_rng(9)
    n = 300
    dates = pd.date_range("2024-01-01", periods=n, freq="h")
    closes = 1.10 * np.exp(np.cumsum(rng.normal(-0.002, 0.001, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.001
    lows = np.minimum(opens, closes) * 0.999
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes,
         "Volume": rng.integers(500, 5000, n).astype(float)},
        index=dates,
    )
