"""
ScraperManager - orchestrates the Classic and Modern scrapers with fallback.

Strategy:
1. Try the primary scraper (default: Classic).
2. If it raises an exception OR returns no usable results, try the
   secondary scraper (Modern) automatically.
3. Health is checked at startup; the order may be flipped at runtime
   based on the latest health-check results.
"""

from __future__ import annotations

from typing import List, Optional

from scrapers.base import BaseScraper, ContentDetail, SearchResult
from scrapers.classic import ClassicScraper
from scrapers.modern import ModernScraper
from utils.logger import get_logger

logger = get_logger(__name__)


class ScraperManager:
    """Manages multiple scrapers with automatic failover."""

    def __init__(self) -> None:
        self.classic = ClassicScraper()
        self.modern = ModernScraper()
        self._primary: BaseScraper = self.classic
        self._secondary: BaseScraper = self.modern
        self._init_done = False

    async def health_check(self) -> dict[str, bool]:
        """Run a health-check on both scrapers; returns {name: alive_bool}."""
        results = {
            "classic": await self.classic.is_alive(),
            "modern": await self.modern.is_alive(),
        }
        logger.info("Scraper health check: {}", results)

        # Reorder primary/secondary based on health
        if results["classic"] and not results["modern"]:
            self._primary, self._secondary = self.classic, self.modern
        elif results["modern"] and not results["classic"]:
            self._primary, self._secondary = self.modern, self.classic
        # If both are alive or both are dead, keep current order
        self._init_done = True
        return results

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------
    async def search(self, query: str) -> List[SearchResult]:
        """Search using the primary scraper, falling back to secondary."""
        query = query.strip()
        if not query:
            return []

        try:
            results = await self._primary.search(query)
            if results:
                return results
            logger.debug("Primary scraper ({}) returned 0 results for '{}'",
                         self._primary.name, query)
        except Exception as exc:
            logger.warning("Primary scraper ({}) error: {}", self._primary.name, exc)

        # Fallback
        try:
            results = await self._secondary.search(query)
            if results:
                logger.info(
                    "Fallback to {} scraper succeeded for '{}' ({} results)",
                    self._secondary.name, query, len(results),
                )
                # Swap primary/secondary for next calls
                self._primary, self._secondary = self._secondary, self._primary
            return results
        except Exception as exc:
            logger.error("Secondary scraper ({}) also failed: {}", self._secondary.name, exc)
            return []

    async def get_content_detail(
        self, mymoviz_id: str, content_type: str = "movie"
    ) -> Optional[ContentDetail]:
        """Fetch content detail with fallback."""
        try:
            detail = await self._primary.get_content_detail(mymoviz_id, content_type)
            if detail and (detail.title_fa or detail.title_en):
                return detail
        except Exception as exc:
            logger.warning("Primary scraper ({}) detail error: {}", self._primary.name, exc)

        try:
            detail = await self._secondary.get_content_detail(mymoviz_id, content_type)
            if detail:
                logger.info(
                    "Fallback to {} scraper succeeded for detail {}",
                    self._secondary.name, mymoviz_id,
                )
                self._primary, self._secondary = self._secondary, self._primary
            return detail
        except Exception as exc:
            logger.error("Secondary scraper ({}) detail also failed: {}",
                         self._secondary.name, exc)
            return None

    async def get_latest_movies(self, limit: int = 20) -> List[SearchResult]:
        """Return latest movies, with fallback."""
        try:
            results = await self._primary.get_latest_movies(limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("Primary get_latest_movies error: {}", exc)
        try:
            return await self._secondary.get_latest_movies(limit)
        except Exception as exc:
            logger.error("Secondary get_latest_movies also failed: {}", exc)
            return []

    async def get_latest_series(self, limit: int = 20) -> List[SearchResult]:
        try:
            results = await self._primary.get_latest_series(limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("Primary get_latest_series error: {}", exc)
        try:
            return await self._secondary.get_latest_series(limit)
        except Exception as exc:
            logger.error("Secondary get_latest_series also failed: {}", exc)
            return []

    async def get_popular(self, limit: int = 20) -> List[SearchResult]:
        try:
            results = await self._primary.get_popular(limit)
            if results:
                return results
        except Exception as exc:
            logger.warning("Primary get_popular error: {}", exc)
        try:
            return await self._secondary.get_popular(limit)
        except Exception as exc:
            logger.error("Secondary get_popular also failed: {}", exc)
            return []

    async def get_latest_updates(self, limit: int = 10) -> tuple[List[SearchResult], List[SearchResult]]:
        """Fetch latest movie and series updates from the modern home page.

        Returns (latest_movies, latest_series).
        Falls back to get_latest_movies/get_latest_series if the modern
        scraper doesn't support get_latest_updates.
        """
        # Try primary scraper
        if hasattr(self._primary, "get_latest_updates"):
            try:
                movies, series = await self._primary.get_latest_updates(limit)
                if movies or series:
                    return movies, series
            except Exception as exc:
                logger.warning("Primary get_latest_updates error: {}", exc)
        # Try secondary scraper
        if hasattr(self._secondary, "get_latest_updates"):
            try:
                movies, series = await self._secondary.get_latest_updates(limit)
                if movies or series:
                    return movies, series
            except Exception as exc:
                logger.warning("Secondary get_latest_updates error: {}", exc)
        # Fallback to the old methods
        try:
            movies = await self.get_latest_movies(limit)
            series = await self.get_latest_series(limit)
            return movies, series
        except Exception as exc:
            logger.error("get_latest_updates fallback failed: {}", exc)
            return [], []


# Module-level singleton
scraper_manager = ScraperManager()
