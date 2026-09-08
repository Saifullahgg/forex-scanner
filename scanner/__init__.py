"""
Forex Signal Scanner package.

A market scanner that fetches live forex data, computes technical
indicators, runs multiple trading strategies, and aggregates the
results into BUY / SELL / NEUTRAL signals.
"""

from .data_provider import ALL_PAIRS, CROSS_PAIRS, EXOTIC_PAIRS, MAJOR_PAIRS
from .engine import ScanResult, Scanner

__all__ = [
    "Scanner",
    "ScanResult",
    "MAJOR_PAIRS",
    "CROSS_PAIRS",
    "EXOTIC_PAIRS",
    "ALL_PAIRS",
]

__version__ = "1.0.0"
