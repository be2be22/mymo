"""
Abstract base scraper and shared dataclasses.

Concrete scrapers (Classic / Modern) inherit from :class:`BaseScraper`
and implement ``search`` and ``get_content_detail``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional

from api.client import HttpClient, http_client
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A single search-result row."""

    title_fa: Optional[str] = None
    title_en: Optional[str] = None
    year: Optional[int] = None
    imdb_rating: Optional[float] = None
    content_type: str = "movie"  # "movie" or "series"
    poster_url: Optional[str] = None
    page_url: Optional[str] = None
    mymoviz_id: Optional[str] = None


@dataclass
class EpisodeDetail:
    """A single episode of a series."""

    season: Optional[int] = None
    episode: Optional[int] = None
    title: Optional[str] = None
    page_url: Optional[str] = None
    qualities: Optional[str] = None
    has_dubbing: bool = False
    has_subtitle: bool = False
    released_at: Optional[str] = None


@dataclass
class ContentDetail:
    """Full detail of a movie or series."""

    mymoviz_id: Optional[str] = None
    content_type: str = "movie"
    title_fa: Optional[str] = None
    title_en: Optional[str] = None
    year: Optional[int] = None
    imdb_rating: Optional[float] = None
    poster_url: Optional[str] = None
    page_url: Optional[str] = None
    summary: Optional[str] = None
    genres: Optional[str] = None
    country: Optional[str] = None
    duration: Optional[str] = None
    qualities: Optional[str] = None
    has_dubbing: bool = False
    has_subtitle: bool = False
    latest_episode: Optional[str] = None
    episodes: List[EpisodeDetail] = field(default_factory=list)
    raw_hash: Optional[str] = None  # used to detect ANY change
    download_links: List[dict] = field(default_factory=list)  # [{"label":..., "url":..., "quality":...}]


class BaseScraper(abc.ABC):
    """Abstract scraper interface.

    Each concrete scraper targets a specific version of the MyMoviz site
    (Classic or Modern). They share the same :class:`HttpClient` instance.
    """

    name: str = "base"

    def __init__(self, http: Optional[HttpClient] = None) -> None:
        self.http = http or http_client
        self.base_url: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @abc.abstractmethod
    async def search(self, query: str) -> List[SearchResult]:
        """Search MyMoviz for ``query`` and return matching results."""

    @abc.abstractmethod
    async def get_content_detail(self, mymoviz_id: str, content_type: str) -> Optional[ContentDetail]:
        """Fetch the full detail for a single content item."""

    async def get_latest_movies(self, limit: int = 20) -> List[SearchResult]:
        """Return recently-added movies (default impl falls back to home scrape)."""
        return []

    async def get_latest_series(self, limit: int = 20) -> List[SearchResult]:
        """Return recently-added series."""
        return []

    async def get_popular(self, limit: int = 20) -> List[SearchResult]:
        """Return popular/trending content."""
        return []

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    async def is_alive(self) -> bool:
        """Return True if the scraper's base URL responds successfully."""
        try:
            await self.http.get(self.base_url)
            return True
        except Exception as exc:  # pragma: no cover - network-dependent
            logger.warning("Scraper {} is_alive failed: {}", self.name, exc)
            return False

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _make_absolute_url(self, url: Optional[str]) -> Optional[str]:
        """Make a relative URL absolute using this scraper's base URL."""
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("/"):
            url = "/" + url
        return settings.classic_base_url + url

    @staticmethod
    def _safe_float(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        try:
            return float(value.replace(",", ".").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            return int("".join(c for c in str(value) if c.isdigit()))
        except (TypeError, ValueError):
            return None
