"""
Unit tests for the cache manager.
"""

from __future__ import annotations

import asyncio
import pytest

from cache.cache_manager import CacheManager


@pytest.mark.asyncio
async def test_cache_set_get() -> None:
    cache = CacheManager(ttl_seconds=10, max_size=10)
    await cache.set("k1", {"v": 1})
    val = await cache.get("k1")
    assert val == {"v": 1}


@pytest.mark.asyncio
async def test_cache_expiry() -> None:
    cache = CacheManager(ttl_seconds=1, max_size=10)
    await cache.set("k1", "v1", ttl=0)  # immediate expiry
    await asyncio.sleep(0.05)
    val = await cache.get("k1")
    assert val is None


@pytest.mark.asyncio
async def test_cache_max_size_eviction() -> None:
    cache = CacheManager(ttl_seconds=60, max_size=3)
    await cache.set("k1", 1)
    await cache.set("k2", 2)
    await cache.set("k3", 3)
    await cache.set("k4", 4)  # should evict k1
    assert await cache.get("k1") is None
    assert await cache.get("k4") == 4


@pytest.mark.asyncio
async def test_cache_delete_and_clear() -> None:
    cache = CacheManager(ttl_seconds=60, max_size=10)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.delete("a")
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    await cache.clear()
    assert await cache.get("b") is None
