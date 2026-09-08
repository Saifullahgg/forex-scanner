"""
Thread-safe TTL cache used to protect the scanner from Yahoo Finance
rate limits when the dashboard auto-refreshes.
"""

import threading
import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """Simple in-memory cache with a time-to-live per entry."""

    def __init__(self, ttl: float = 300.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._store: Dict[Tuple, Tuple[float, Any]] = {}

    def get(self, key: Tuple) -> Optional[Any]:
        """Return the cached value for key, or None if missing/expired."""
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            ts, value = item
            if time.monotonic() - ts > self.ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: Tuple, value: Any) -> None:
        """Store value under key with the current time as timestamp."""
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
