"""Tests for the thread-safe TTL cache used by the web app."""

import threading
import time

import pytest

from webapp.cache import TTLCache


def test_get_missing_returns_none():
    cache = TTLCache(ttl=10)
    assert cache.get(("EURUSD", "1h", "1mo")) is None


def test_set_then_get_roundtrip():
    cache = TTLCache(ttl=10)
    cache.set(("EURUSD", "1h", "1mo"), [1, 2, 3])
    assert cache.get(("EURUSD", "1h", "1mo")) == [1, 2, 3]


def test_expired_entry_is_removed():
    cache = TTLCache(ttl=0.05)
    cache.set(("GBPUSD", "15m", "5d"), "cached")
    assert cache.get(("GBPUSD", "15m", "5d")) == "cached"
    time.sleep(0.1)
    assert cache.get(("GBPUSD", "15m", "5d")) is None
    assert len(cache) == 0


def test_len_reflects_store_size():
    cache = TTLCache(ttl=10)
    assert len(cache) == 0
    cache.set(("A",), 1)
    cache.set(("B",), 2)
    assert len(cache) == 2
    cache.set(("A",), 3)  # overwrite does not grow
    assert len(cache) == 2


def test_clear_removes_all():
    cache = TTLCache(ttl=10)
    cache.set(("EURUSD",), 1)
    cache.set(("USDJPY",), 2)
    cache.clear()
    assert len(cache) == 0
    assert cache.get(("EURUSD",)) is None


def test_distinct_keys_are_isolated():
    cache = TTLCache(ttl=10)
    cache.set(("EURUSD", "1h"), "hourly")
    cache.set(("EURUSD", "1d"), "daily")
    assert cache.get(("EURUSD", "1h")) == "hourly"
    assert cache.get(("EURUSD", "1d")) == "daily"


def test_ttl_zero_expires_immediately():
    cache = TTLCache(ttl=0)
    cache.set(("X",), 42)
    assert cache.get(("X",)) is None


def test_concurrent_set_and_get_is_safe():
    cache = TTLCache(ttl=5)
    errors = []

    def writer(i: int) -> None:
        try:
            for j in range(200):
                cache.set((f"pair{i}", "1h", "1mo"), i * 1000 + j)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # Every key written should be retrievable (last writer wins).
    for i in range(8):
        assert cache.get((f"pair{i}", "1h", "1mo")) is not None
