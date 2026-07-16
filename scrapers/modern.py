"""
Scraper for the Modern (_modern) version of MyMoviz.co.

URL pattern:
    Home:        https://mymoviz.co/_modern/home
    Search:      https://mymoviz.co/_modern/search?q=<query>
    Movie page:  https://mymoviz.co/_modern/movie/<slug>
    Series page: https://mymoviz.co/_modern/series/<slug>

The Modern version uses a more SPA-like layout, so we lean on data-*
attributes and modern CSS selectors. Falls back to classic-style
selectors when needed.
"""

from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config.settings import settings
from scrapers.base import BaseScraper, ContentDetail, EpisodeDetail, SearchResult
from utils.logger import get_logger

logger = get_logger(__name__)


class ModernScraper(BaseScraper):
    """Scraper for the modern (_modern) version of MyMoviz."""

    name = "modern"

    def __init__(self, http=None) -> None:
        super().__init__(http=http)
        self.base_url = settings.classic_base_url  # absolute URL builder base
        self.modern_base = settings.modern_base_url  # full modern home URL

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def search(self, query: str) -> List[SearchResult]:
        query = query.strip()
        if not query:
            return []

        # Try modern search endpoint first
        candidates = [
            f"{self.modern_base}/search?q={quote_plus(query)}",
            f"{settings.classic_base_url}/_modern/search?q={quote_plus(query)}",
        ]

        html: Optional[str] = None
        for url in candidates:
            try:
                html = await self.http.get(url)
                break
            except Exception as exc:
                logger.debug("ModernScraper search candidate failed: {} - {}", url, exc)

        if not html:
            logger.warning("ModernScraper search exhausted all candidates for '{}'", query)
            return []

        soup = BeautifulSoup(html, "lxml")
        return self._parse_modern_grid(soup)

    # ------------------------------------------------------------------
    # Latest / Popular
    # ------------------------------------------------------------------
    async def get_latest_movies(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(self.modern_base)
        except Exception as exc:
            logger.warning("ModernScraper get_latest_movies failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_modern_grid(soup)
        return [r for r in results if r.content_type == "movie"][:limit]

    async def get_latest_series(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(f"{settings.classic_base_url}/_modern/series")
        except Exception as exc:
            logger.warning("ModernScraper get_latest_series failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_modern_grid(soup)
        return [r for r in results if r.content_type == "series"][:limit]

    async def get_popular(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(f"{settings.classic_base_url}/_modern/popular")
        except Exception as exc:
            logger.warning("ModernScraper get_popular failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_modern_grid(soup)
        return results[:limit]

    async def get_latest_updates(self, limit: int = 10) -> tuple[List[SearchResult], List[SearchResult]]:
        """Fetch latest movie updates and latest series updates from modern home page.

        Returns (latest_movies, latest_series) - each up to `limit` items.
        Uses the two dedicated sections on the modern home page:
        - "آخرین بروزرسانی فیلم ها" (latest movie updates)
        - "سریال‌های به‌روز شده" (updated series)
        """
        try:
            html = await self.http.get(self.modern_base)
        except Exception as exc:
            logger.warning("ModernScraper get_latest_updates failed: {}", exc)
            return [], []

        soup = BeautifulSoup(html, "lxml")
        latest_movies: List[SearchResult] = []
        latest_series: List[SearchResult] = []

        # Find the mv-row__track sections
        tracks = soup.select(".mv-row__track")
        for track in tracks:
            # Determine which section this is by looking at the parent's heading
            section = track.find_parent("section")
            if not section:
                continue
            heading = section.select_one("h2, h3, .mv-row__title")
            if not heading:
                continue
            heading_text = heading.get_text(strip=True)

            cards = track.select("a.mv-card")
            for card in cards:
                result = self._parse_modern_card_v2(card)
                if result and (result.title_fa or result.title_en):
                    if "فیلم" in heading_text:
                        result.content_type = "movie"
                        latest_movies.append(result)
                    elif "سریال" in heading_text:
                        result.content_type = "series"
                        latest_series.append(result)

        return latest_movies[:limit], latest_series[:limit]

    def _parse_modern_card_v2(self, card) -> Optional[SearchResult]:
        """Parse a modern mv-card element from the home page tracks."""
        href = card.get("href", "")
        data_guid = card.get("data-guid", "")

        content_type = "movie"
        # Check if it's a series (has mv-card__ep = episode info)
        if card.select_one(".mv-card__ep"):
            content_type = "series"

        # Title
        title_en_el = card.select_one(".mv-card__title")
        title_en = title_en_el.get_text(strip=True) if title_en_el else None
        title_fa_el = card.select_one(".mv-card__title-fa")
        title_fa = title_fa_el.get_text(strip=True) if title_fa_el else None

        # Poster
        img = card.select_one(".mv-card__img")
        poster = None
        if img:
            poster = img.get("data-src") or img.get("src")
            if poster:
                poster = poster.replace("/./", "/")

        # Year
        year = None
        sub_el = card.select_one(".mv-card__sub")
        if sub_el:
            import re
            m = re.search(r"(\d{4})", sub_el.get_text())
            if m:
                year = int(m.group(1))

        # Rating (IMDb)
        rating = None
        rating_el = card.select_one(".mv-card__rate--imdb")
        if rating_el:
            import re
            m = re.search(r"(\d+\.?\d*)", rating_el.get_text())
            if m:
                rating = float(m.group(1))

        # Plot/summary
        plot_el = card.select_one(".mv-card__plot")
        summary = plot_el.get_text(strip=True) if plot_el else None

        # Latest episode (for series)
        latest_ep_el = card.select_one(".mv-card__ep")
        latest_episode = latest_ep_el.get_text(strip=True) if latest_ep_el else None

        # Genres
        genres = []
        for g in card.select(".mv-card__genre"):
            t = g.get_text(strip=True)
            if t:
                genres.append(t)
        genres_str = ", ".join(genres) if genres else None

        # Build page_url and mymoviz_id
        page_url = self._make_absolute_url(href) if href else None
        mymoviz_id = data_guid or None
        if href:
            import re
            m = re.search(r"/_modern/title/(\d+)", href)
            if m:
                mymoviz_id = m.group(1)

        result = SearchResult(
            title_fa=title_fa,
            title_en=title_en,
            year=year,
            imdb_rating=rating,
            content_type=content_type,
            poster_url=self._make_absolute_url(poster) if poster else None,
            page_url=page_url,
            mymoviz_id=mymoviz_id,
        )
        # Stash extra info
        result._summary = summary  # type: ignore[attr-defined]
        result._latest_episode = latest_episode  # type: ignore[attr-defined]
        result._genres = genres_str  # type: ignore[attr-defined]
        return result

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    async def get_content_detail(
        self, mymoviz_id: str, content_type: str = "movie"
    ) -> Optional[ContentDetail]:
        if not mymoviz_id:
            return None

        if mymoviz_id.startswith("http"):
            url = mymoviz_id
        else:
            # If mymoviz_id already starts with "tvshows/" or "movie/", don't
            # re-prefix with another section (it would create /_modern/series/tvshows/...).
            stripped = mymoviz_id.lstrip("/")
            if stripped.startswith("tvshows/") or stripped.startswith("movie/"):
                url = f"{settings.classic_base_url}/_modern/{stripped}"
            else:
                section = "movie" if content_type == "movie" else "series"
                url = f"{settings.classic_base_url}/_modern/{section}/{mymoviz_id}"

        try:
            html = await self.http.get(url)
        except Exception as exc:
            logger.warning("ModernScraper detail failed for {}: {}", url, exc)
            return None

        soup = BeautifulSoup(html, "lxml")
        return self._parse_modern_detail(soup, mymoviz_id, content_type, url)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_modern_grid(self, soup: BeautifulSoup) -> List[SearchResult]:
        results: List[SearchResult] = []
        cards = soup.select(
            "[class*=MovieCard], [class*=movie-card], [class*=series-card], "
            "[class*=CardItem], [class*=card-item], [data-movie-id], [data-series-id], "
            ".MuiCard-root, article"
        )
        if not cards:
            cards = soup.select("a[href*='/movie/'], a[href*='/series/']")
            cards = list({c for c in cards}) if cards else []

        for card in cards:
            r = self._parse_modern_card(card)
            if r and (r.title_fa or r.title_en):
                results.append(r)
        return results

    def _parse_modern_card(self, card) -> Optional[SearchResult]:
        href = None
        link = card.find("a", href=True) if hasattr(card, "find") else None
        if link:
            href = link["href"]
        if not href and card.has_attr("href"):
            href = card["href"]

        content_type = "movie"
        if href and "/series/" in href:
            content_type = "series"

        mymoviz_id = None
        if href:
            m = re.search(r"/(?:movie|series)/([^/?#]+)", href)
            if m:
                mymoviz_id = m.group(1)

        # Try data-* attributes first (modern sites love them)
        title_fa = card.get("data-title-fa") or card.get("data-title")
        title_en = card.get("data-title-en") or card.get("data-original-title")
        year = self._safe_int(card.get("data-year"))
        rating = self._safe_float(card.get("data-rating"))
        poster = card.get("data-poster") or card.get("data-image")

        if not title_fa:
            t_el = card.select_one(
                "[class*=title], [class*=Title], h2, h3, h4, [class*=name]"
            )
            if t_el:
                title_fa = t_el.get_text(strip=True)
        if not title_en:
            e_el = card.select_one("[class*=english], [class*=original], [class*=TitleEn]")
            if e_el:
                title_en = e_el.get_text(strip=True)
        if not poster:
            img = card.find("img")
            if img:
                poster = img.get("src") or img.get("data-src")
        if year is None:
            y_el = card.select_one("[class*=year], [class*=Year], [class*=date]")
            if y_el:
                year = self._safe_int(y_el.get_text(strip=True))
        if rating is None:
            r_el = card.select_one("[class*=rating], [class*=Rating], [class*=imdb]")
            if r_el:
                rating = self._safe_float(r_el.get_text(strip=True))

        return SearchResult(
            title_fa=title_fa,
            title_en=title_en,
            year=year,
            imdb_rating=rating,
            content_type=content_type,
            poster_url=self._make_absolute_url(poster) if poster else None,
            page_url=self._make_absolute_url(href) if href else None,
            mymoviz_id=mymoviz_id,
        )

    def _parse_modern_detail(
        self,
        soup: BeautifulSoup,
        mymoviz_id: str,
        content_type: str,
        url: str,
    ) -> Optional[ContentDetail]:
        detail = ContentDetail(
            mymoviz_id=mymoviz_id,
            content_type=content_type,
            page_url=url,
        )

        # Title
        title_el = soup.select_one(
            "h1, [class*=MovieTitle], [class*=SeriesTitle], [class*=DetailTitle]"
        )
        if title_el:
            detail.title_fa = title_el.get_text(strip=True)
        en_el = soup.select_one(
            "[class*=EnglishTitle], [class*=OriginalTitle], [class*=TitleEn]"
        )
        if en_el:
            detail.title_en = en_el.get_text(strip=True)

        # Poster
        img = soup.select_one("[class*=Poster] img, [class*=poster] img, [class*=Cover] img")
        if img:
            detail.poster_url = self._make_absolute_url(
                img.get("src") or img.get("data-src")
            )

        # Summary
        summary_el = soup.select_one(
            "[class*=Summary], [class*=Description], [class*=Plot], [class*=Storyline]"
        )
        if summary_el:
            detail.summary = summary_el.get_text(" ", strip=True)

        # Meta via data attributes / labeled rows
        meta = self._extract_modern_meta(soup)
        detail.genres = meta.get("ژانر") or meta.get("genre") or meta.get("Genre")
        detail.country = meta.get("کشور") or meta.get("country") or meta.get("Country")
        detail.duration = meta.get("مدت") or meta.get("duration") or meta.get("Runtime")
        detail.year = self._safe_int(
            meta.get("سال") or meta.get("year") or meta.get("Year")
        )

        # IMDb
        imdb_el = soup.select_one("[class*=IMDB], [class*=imdb], [class*=Rating]")
        if imdb_el:
            detail.imdb_rating = self._safe_float(imdb_el.get_text(strip=True))

        # Qualities
        q_els = soup.select("[class*=Quality], [class*=quality]")
        qs = [q.get_text(strip=True) for q in q_els if q.get_text(strip=True)]
        if qs:
            detail.qualities = ", ".join(dict.fromkeys(qs))

        # Dub/Sub
        full_text = soup.get_text(" ", strip=True)
        detail.has_dubbing = "دوبله" in full_text or "dubbing" in full_text.lower()
        detail.has_subtitle = "زیرنویس" in full_text or "subtitle" in full_text.lower()

        # Episodes for series
        if content_type == "series":
            detail.episodes = self._parse_modern_episodes(soup)
            if detail.episodes:
                ep = detail.episodes[0]
                detail.latest_episode = f"فصل {ep.season or '?'} قسمت {ep.episode or '?'}"

        # Hash
        import hashlib
        body_text = soup.get_text(" ", strip=True)
        detail.raw_hash = hashlib.md5(body_text.encode("utf-8")).hexdigest()[:16]

        return detail

    def _extract_modern_meta(self, soup: BeautifulSoup) -> dict:
        meta: dict[str, Optional[str]] = {}
        for row in soup.select(
            "[class*=MetaRow], [class*=InfoRow], [class*=DetailRow], "
            "[class*=meta-item], [class*=info-item], li, .row"
        ):
            label = row.select_one(
                "[class*=Label], [class*=Key], [class*=meta-label], .label, .key"
            )
            value = row.select_one(
                "[class*=Value], [class*=meta-value], .value"
            )
            if label and value:
                key = label.get_text(strip=True).rstrip(":")
                meta[key] = value.get_text(" ", strip=True)
        return meta

    def _parse_modern_episodes(self, soup: BeautifulSoup) -> List[EpisodeDetail]:
        episodes: List[EpisodeDetail] = []
        ep_els = soup.select(
            "[class*=EpisodeItem], [class*=episode-item], [class*=EpisodeRow], "
            "[class*=episode-row], [data-episode], [class*=Episode]"
        )
        for ep_el in ep_els:
            ep = EpisodeDetail()
            text = ep_el.get_text(" ", strip=True)

            # data-* attributes (modern)
            ep.season = self._safe_int(ep_el.get("data-season"))
            ep.episode = self._safe_int(ep_el.get("data-episode"))
            ep.page_url = self._make_absolute_url(ep_el.get("data-url"))

            if ep.season is None or ep.episode is None:
                m = re.search(r"S(\d+)E(\d+)", text, re.I)
                if m:
                    ep.season = int(m.group(1))
                    ep.episode = int(m.group(2))
                else:
                    m2 = re.search(r"فصل\s*(\d+).*?قسمت\s*(\d+)", text)
                    if m2:
                        ep.season = int(m2.group(1))
                        ep.episode = int(m2.group(2))

            link = ep_el.find("a", href=True)
            if link and not ep.page_url:
                ep.page_url = self._make_absolute_url(link["href"])

            q_els = ep_el.select("[class*=Quality], [class*=quality]")
            if q_els:
                ep.qualities = ", ".join(q.get_text(strip=True) for q in q_els)

            ep.has_dubbing = "دوبله" in text
            ep.has_subtitle = "زیرنویس" in text
            ep.title = text[:120]
            episodes.append(ep)

        episodes.sort(key=lambda e: (e.season or 0, e.episode or 0), reverse=True)
        return episodes
