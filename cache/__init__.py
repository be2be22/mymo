"""In-memory cache package - 30-minute TTL for search results."""

from cache.cache_manager import CacheManager, cache

__all__ = ["CacheManager", "cache"]
