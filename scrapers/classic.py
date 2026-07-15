"""
Scraper for the Classic version of MyMoviz.co.

URL pattern:
    Home:        https://mymoviz.co
    Search:      https://mymoviz.co/search?q=<query>
    Movie page:  https://mymoviz.co/movie/<slug>
    Series page: https://mymoviz.co/series/<slug>

The selectors below are conservative and degrade gracefully. If MyMoviz
changes its markup, the :class:`ScraperManager` will fall back to the
Modern scraper automatically.
"""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ContentDetail, EpisodeDetail, SearchResult
from utils.logger import get_logger

logger = get_logger(__name__)


class ClassicScraper(BaseScraper):
    """Scraper for the classic (non-SPA) version of MyMoviz."""

    name = "classic"

    def __init__(self, http=None) -> None:
        super().__init__(http=http)
        from config.settings import settings

        self.base_url = settings.classic_base_url

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def search(self, query: str) -> List[SearchResult]:
        """Search via the classic search endpoint and parse cards."""
        query = query.strip()
        if not query:
            return []

        url = f"{self.base_url}/search?q={quote_plus(query)}"
        try:
            html = await self.http.get(url)
        except Exception as exc:
            logger.warning("ClassicScraper search failed for '{}': {}", query, exc)
            return []

        soup = BeautifulSoup(html, "lxml")
        return self._parse_card_grid(soup)

    # ------------------------------------------------------------------
    # Latest / Popular
    # ------------------------------------------------------------------
    async def get_latest_movies(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(self.base_url)
        except Exception as exc:
            logger.warning("ClassicScraper get_latest_movies failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_card_grid(soup)
        return [r for r in results if r.content_type == "movie"][:limit]

    async def get_latest_series(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(f"{self.base_url}/series")
        except Exception as exc:
            logger.warning("ClassicScraper get_latest_series failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_card_grid(soup)
        return [r for r in results if r.content_type == "series"][:limit]

    async def get_popular(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(f"{self.base_url}/popular")
        except Exception as exc:
            logger.warning("ClassicScraper get_popular failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_card_grid(soup)
        return results[:limit]

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    async def get_content_detail(
        self, mymoviz_id: str, content_type: str = "movie"
    ) -> Optional[ContentDetail]:
        """Fetch a movie or series detail page."""
        if not mymoviz_id:
            return None

        # mymoviz_id may be a full URL or a slug
        if mymoviz_id.startswith("http"):
            url = mymoviz_id
        else:
            section = "movie" if content_type == "movie" else "series"
            url = f"{self.base_url}/{section}/{mymoviz_id}"

        try:
            html = await self.http.get(url)
        except Exception as exc:
            logger.warning("ClassicScraper detail failed for {}: {}", url, exc)
            return None

        soup = BeautifulSoup(html, "lxml")
        return self._parse_detail_page(soup, mymoviz_id, content_type, url)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_card_grid(self, soup: BeautifulSoup) -> List[SearchResult]:
        """Parse the grid of cards returned on listing/search pages."""
        results: List[SearchResult] = []

        # MyMoviz typically renders cards as <div class="card"> or <article>
        # We try several common selectors for robustness.
        cards = soup.select(
            "div.movie-card, div.card, article.card, .item, .movie-item, "
            ".post, .product-card, [data-id]"
        )
        if not cards:
            # Fallback: any element with a poster image and a link
            cards = soup.select("a[href*='/movie/'], a[href*='/series/']")
            cards = list({c.find_parent() or c for c in cards}) if cards else []

        for card in cards:
            result = self._parse_single_card(card)
            if result and (result.title_fa or result.title_en):
                results.append(result)

        return results

    def _parse_single_card(self, card) -> Optional[SearchResult]:
        """Extract a :class:`SearchResult` from a single card element."""
        # Link
        link = card.find("a", href=True)
        href = link["href"] if link else None
        if href and ("/movie/" in href or "/series/" in href):
            content_type = "series" if "/series/" in href else "movie"
        else:
            content_type = "movie"

        page_url = self._make_absolute_url(href) if href else None
        mymoviz_id = None
        if href:
            m = re.search(r"/(movie|series)/([^/?#]+)", href)
            if m:
                mymoviz_id = m.group(2)

        # Poster
        poster = None
        img = card.find("img")
        if img:
            poster = img.get("src") or img.get("data-src") or img.get("data-original")
            poster = self._make_absolute_url(poster)

        # Title
        title_fa = None
        title_en = None
        title_el = card.select_one(".title, .movie-title, h3, h4, .name, .card-title")
        if title_el:
            title_fa = title_el.get_text(strip=True)
        en_el = card.select_one(".title-en, .english-title, .original-title")
        if en_el:
            title_en = en_el.get_text(strip=True)

        # Year
        year = None
        year_el = card.select_one(".year, .release-year, .date")
        if year_el:
            year = self._safe_int(year_el.get_text(strip=True))

        # Rating
        rating = None
        rating_el = card.select_one(".rating, .imdb, .score, .imdb-rating")
        if rating_el:
            rating = self._safe_float(rating_el.get_text(strip=True))

        return SearchResult(
            title_fa=title_fa,
            title_en=title_en,
            year=year,
            imdb_rating=rating,
            content_type=content_type,
            poster_url=poster,
            page_url=page_url,
            mymoviz_id=mymoviz_id,
        )

    def _parse_detail_page(
        self,
        soup: BeautifulSoup,
        mymoviz_id: str,
        content_type: str,
        url: str,
    ) -> Optional[ContentDetail]:
        """Parse a movie/series detail page."""
        detail = ContentDetail(
            mymoviz_id=mymoviz_id,
            content_type=content_type,
            page_url=url,
        )

        # Title
        title_el = soup.select_one(
            "h1.movie-title, h1.title, h1.series-title, .movie-detail h1, h1"
        )
        if title_el:
            detail.title_fa = title_el.get_text(strip=True)
        en_el = soup.select_one(
            ".english-title, .original-title, .title-en, .movie-detail .original"
        )
        if en_el:
            detail.title_en = en_el.get_text(strip=True)

        # Poster
        img = soup.select_one(".poster img, .movie-poster img, .cover img, img.poster")
        if img:
            detail.poster_url = self._make_absolute_url(
                img.get("src") or img.get("data-src")
            )

        # Summary
        summary_el = soup.select_one(
            ".summary, .description, .plot, .storyline, .movie-detail .description, [class*=summary]"
        )
        if summary_el:
            detail.summary = summary_el.get_text(" ", strip=True)

        # Meta info - try to find labels
        meta = self._extract_meta_table(soup)
        detail.genres = meta.get("ژانر") or meta.get("Genre") or meta.get("genre")
        detail.country = meta.get("کشور") or meta.get("Country") or meta.get("country")
        detail.duration = meta.get("مدت") or meta.get("Duration") or meta.get("Runtime")
        detail.year = self._safe_int(meta.get("سال") or meta.get("Year") or meta.get("year"))

        # IMDb rating
        imdb_el = soup.select_one(".imdb-rating, .imdb, [class*=imdb]")
        if imdb_el:
            detail.imdb_rating = self._safe_float(imdb_el.get_text(strip=True))

        # Qualities
        qualities = []
        for q in soup.select(".quality, .qualities, [class*=quality]"):
            text = q.get_text(strip=True)
            if text and text not in qualities:
                qualities.append(text)
        if qualities:
            detail.qualities = ", ".join(qualities)

        # Dubbing / Subtitle flags
        text_lower = soup.get_text(" ", strip=True).lower()
        detail.has_dubbing = "دوبله" in soup.get_text() or "dubbing" in text_lower
        detail.has_subtitle = "زیرنویس" in soup.get_text() or "subtitle" in text_lower

        # Episodes (for series)
        if content_type == "series":
            detail.episodes = self._parse_episodes(soup)
            if detail.episodes:
                ep = detail.episodes[0]
                detail.latest_episode = f"فصل {ep.season or '?'} قسمت {ep.episode or '?'}"

        # Compute a raw hash to detect ANY change for scheduler use
        import hashlib
        body_text = soup.get_text(" ", strip=True)
        detail.raw_hash = hashlib.md5(body_text.encode("utf-8")).hexdigest()[:16]

        return detail

    def _extract_meta_table(self, soup: BeautifulSoup) -> dict:
        """Extract key-value metadata from the detail page.

        Looks for both <table> rows and labeled <div>/<li> elements.
        """
        meta: dict[str, Optional[str]] = {}

        # Try table rows
        for row in soup.select("table tr, .info-row, .meta-row, .detail-row li, ul.info li"):
            cells = row.find_all(["td", "th", "span", "div", "b", "strong"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(" ", strip=True)
                if key:
                    meta[key] = value

        # Try <div class="row"><span class="label">...</span><span class="value">...</span></div>
        for row in soup.select(".row, .meta-item, .info-item"):
            label = row.select_one(".label, .key, .meta-label")
            value = row.select_one(".value, .meta-value")
            if label and value:
                key = label.get_text(strip=True).rstrip(":")
                meta[key] = value.get_text(" ", strip=True)

        return meta

    def _parse_episodes(self, soup: BeautifulSoup) -> List[EpisodeDetail]:
        """Extract episode list from a series detail page."""
        episodes: List[EpisodeDetail] = []

        # Try various episode selectors
        ep_els = soup.select(
            ".episode, .episode-item, .episodes li, .episode-list .item, "
            "tr.episode, [class*=episode]"
        )
        for ep_el in ep_els:
            ep = EpisodeDetail()
            text = ep_el.get_text(" ", strip=True)

            # Try to extract season/episode numbers
            m = re.search(r"(?:فصل|S|Season)\s*(\d+)\s*(?:قسمت|E|Episode)\s*(\d+)", text, re.I)
            if m:
                ep.season = int(m.group(1))
                ep.episode = int(m.group(2))
            else:
                m2 = re.search(r"S(\d+)E(\d+)", text, re.I)
                if m2:
                    ep.season = int(m2.group(1))
                    ep.episode = int(m2.group(2))

            link = ep_el.find("a", href=True)
            if link:
                ep.page_url = self._make_absolute_url(link["href"])

            qualities = ep_el.select(".quality, [class*=quality]")
            if qualities:
                ep.qualities = ", ".join(q.get_text(strip=True) for q in qualities)

            ep_text = ep_el.get_text(" ", strip=True)
            ep.has_dubbing = "دوبله" in ep_text
            ep.has_subtitle = "زیرنویس" in ep_text
            ep.title = text[:120]
            episodes.append(ep)

        # Sort: latest first
        episodes.sort(
            key=lambda e: (e.season or 0, e.episode or 0), reverse=True
        )
        return episodes
