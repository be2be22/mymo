"""
Web scrapers for MyMoviz.co - supports both Classic and Modern versions.

The :class:`ScraperManager` automatically falls back from one scraper to
the other when the primary fails or returns no usable data.
"""

from scrapers.manager import ScraperManager, scraper_manager
from scrapers.base import (
    BaseScraper,
    ContentDetail,
    DownloadGroup,
    EpisodeDetail,
    SearchResult,
)

__all__ = [
    "BaseScraper",
    "ContentDetail",
    "DownloadGroup",
    "EpisodeDetail",
    "SearchResult",
    "ScraperManager",
    "scraper_manager",
]
