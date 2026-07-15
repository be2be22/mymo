"""
Simple TTL cache for search results and metadata.

The cache is in-memory and bounded by ``CACHE_MAX_SIZE`` entries with a
default TTL of 30 minutes (configurable via ``CACHE_TTL_SECONDS``). When
the cache is full, the oldest entries are evicted first (FIFO).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Optional

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Thread-safe (asyncio-safe) bounded TTL cache."""

    def __init__(
        self,
        ttl_seconds: int = settings.cache_ttl_seconds,
        max_size: int = settings.cache_max_size,
    ) -> None:
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Return the cached value if present and not expired; else None."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            # Mark as recently used
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store ``value`` under ``key`` with optional per-entry TTL override."""
        async with self._lock:
            expires_at = time.monotonic() + (ttl or self._ttl)
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            # Evict oldest entries if over capacity
            while len(self._store) > self._max_size:
                evicted_key, _ = self._store.popitem(last=False)
                logger.debug("Cache evicted key: {}", evicted_key)

    async def delete(self, key: str) -> None:
        """Remove ``key`` from the cache if present."""
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        """Clear the entire cache."""
        async with self._lock:
            self._store.clear()

    async def size(self) -> int:
        """Return the current number of entries."""
        async with self._lock:
            return len(self._store)

    async def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns the number removed."""
        now = time.monotonic()
        async with self._lock:
            expired_keys = [k for k, (exp, _) in self._store.items() if now > exp]
            for k in expired_keys:
                self._store.pop(k, None)
            if expired_keys:
                logger.debug("Cache cleanup: removed {} expired entries", len(expired_keys))
            return len(expired_keys)


# Module-level singleton
cache = CacheManager()
