"""HTTP API client package - aiohttp-based with retry, backoff, rate limiting."""

from api.client import HttpClient

__all__ = ["HttpClient"]
