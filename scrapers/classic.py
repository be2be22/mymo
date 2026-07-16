"""
Scraper for the Classic version of MyMoviz.co.

URL pattern (verified against live site):
    Home:        https://mymoviz.co
    Search:      https://mymoviz.co/search/?q=<query>
    Movie page:  https://mymoviz.co/tt<imdb_id>/<slug>  OR  https://mymoviz.co/movie/<slug>
    Series page: https://mymoviz.co/tvshows/<slug>  OR  https://mymoviz.co/series/<slug>
    Sign in:     https://mymoviz.co/signin

HTML structure of a card (verified):
    <article class="movie clearfix">
      <a class="movie-poster" href="/tt1375666/Inception-2010">
        <img data-src="https://imgsources.cc/...jpg"/>
      </a>
      <h2 class="movie-title"><a href="/tt1375666/Inception-2010">Inception <span>(2010)</span></a></h2>
      <h2 class="movie-titlep"><a href="...">تلقین</a></h2>  <!-- Persian title -->
      <span class="movie-rating">8.8</span>
      <span class="text-blue bold">BluRay 1080p</span>     <!-- Quality -->
      ... "با زیرنویس فارسی" / "دوبله فارسی" ...
    </article>

The selectors below are conservative and degrade gracefully. If MyMoviz
changes its markup, the :class:`ScraperManager` will fall back to the
Modern scraper automatically.
"""

from __future__ import annotations

import hashlib
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

        url = f"{self.base_url}/search/?q={quote_plus(query)}"
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
            html = await self.http.get(f"{self.base_url}/tvshows")
        except Exception as exc:
            logger.warning("ClassicScraper get_latest_series failed: {}", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        results = self._parse_card_grid(soup)
        return [r for r in results if r.content_type == "series"][:limit]

    async def get_popular(self, limit: int = 20) -> List[SearchResult]:
        try:
            html = await self.http.get(f"{self.base_url}/?oB=8&limit=50")
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
            url = f"{self.base_url}/{mymoviz_id}"

        logger.info("ClassicScraper fetching detail: {}", url)
        try:
            html = await self.http.get(url)
        except Exception as exc:
            logger.warning("ClassicScraper detail HTTP failed for {}: {}", url, exc)
            return None

        if not html or len(html) < 500:
            logger.warning(
                "ClassicScraper detail got empty/short HTML ({} bytes) for {}",
                len(html) if html else 0, url,
            )
            return None

        soup = BeautifulSoup(html, "lxml")
        detail = self._parse_detail_page(soup, mymoviz_id, content_type, url)
        if detail is None:
            logger.warning("ClassicScraper _parse_detail_page returned None for {}", url)
        elif not (detail.title_fa or detail.title_en):
            logger.warning(
                "ClassicScraper detail parsed but no title found for {} (page size={})",
                url, len(html),
            )
            # Log a snippet of the HTML for debugging - look at the <title> tag and first 800 chars
            page_title_el = soup.select_one("title")
            page_title_text = page_title_el.get_text(strip=True) if page_title_el else "(no title tag)"
            logger.warning("Page <title>='{}', body snippet: {}", page_title_text[:200], html[:800])
            # Also log any h1/h2 we find
            for h in soup.select("h1, h2")[:5]:
                logger.warning("  Found {}: {}", h.name, h.get_text(" ", strip=True)[:200])
        else:
            logger.info(
                "ClassicScraper detail OK for {}: fa='{}' en='{}'",
                url, detail.title_fa, detail.title_en,
            )
        return detail

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_card_grid(self, soup: BeautifulSoup) -> List[SearchResult]:
        """Parse the grid of cards returned on listing/search pages."""
        results: List[SearchResult] = []

        # MyMoviz uses <article class="movie clearfix"> for both movies and series
        cards = soup.select("article.movie, .movie-item, .box-movies .movie, .item-movie")
        if not cards:
            # Fallback: any element linking to a /ttXXX or /tvshows path
            cards = soup.select("a[href*='/tt'], a[href*='/tvshows/']")
            # Deduplicate by parent
            seen_parents = set()
            unique_cards = []
            for c in cards:
                parent = c.find_parent(["article", "div", "li"]) or c
                if id(parent) not in seen_parents:
                    seen_parents.add(id(parent))
                    unique_cards.append(parent)
            cards = unique_cards

        for card in cards:
            result = self._parse_single_card(card)
            if result and (result.title_fa or result.title_en):
                results.append(result)

        return results

    def _parse_single_card(self, card) -> Optional[SearchResult]:
        """Extract a :class:`SearchResult` from a single card element."""
        # Detect content type from any link inside the card
        href = None
        for link in card.find_all("a", href=True):
            href = link["href"]
            if "/tvshows/" in href or "/series/" in href:
                content_type = "series"
                break
            if "/tt" in href or "/movie/" in href:
                content_type = "movie"
                break
        else:
            if href:
                content_type = "movie"
            else:
                return None

        page_url = self._make_absolute_url(href) if href else None
        mymoviz_id = None
        if href:
            # Strip query string and take last path segment
            path = href.split("?")[0].split("#")[0].strip("/")
            if path:
                mymoviz_id = path

        # Poster
        poster = None
        img = card.find("img")
        if img:
            poster = img.get("data-src") or img.get("src") or img.get("data-original")
            if poster:
                poster = poster.replace("/./", "/")
            poster = self._make_absolute_url(poster)

        # Titles: MyMoviz has both Persian (movie-titlep) and English (movie-title)
        title_fa = None
        title_en = None

        fa_el = card.select_one(".movie-titlep, .title-fa, .persian-title")
        if fa_el:
            title_fa = fa_el.get_text(strip=True)

        en_el = card.select_one(".movie-title, .title-en, .english-title")
        if en_el:
            en_text = en_el.get_text(" ", strip=True)
            # Extract year from "( 2010 )" pattern
            year_match = re.search(r"\(\s*(\d{4})\s*\)", en_text)
            if year_match:
                year = int(year_match.group(1))
                # Remove the year from the title
                en_text = re.sub(r"\(\s*\d{4}\s*\)", "", en_text).strip()
            else:
                year = None
            title_en = en_text or None
        else:
            year = None

        # Fallback for year if not found in title
        if year is None:
            year_el = card.select_one(".year, .release-year, .date")
            if year_el:
                year = self._safe_int(year_el.get_text(strip=True))

        # Rating
        rating = None
        rating_el = card.select_one(".movie-rating, .rating, .imdb, .score, .imdb-rating")
        if rating_el:
            rating = self._safe_float(rating_el.get_text(strip=True))

        # Detect dubbing / subtitle from card text
        card_text = card.get_text(" ", strip=True)
        has_dubbing = "دوبله" in card_text
        has_subtitle = "زیرنویس" in card_text

        result = SearchResult(
            title_fa=title_fa,
            title_en=title_en,
            year=year,
            imdb_rating=rating,
            content_type=content_type,
            poster_url=poster,
            page_url=page_url,
            mymoviz_id=mymoviz_id,
        )
        # Stash extra info for detail page use
        result._has_dubbing = has_dubbing  # type: ignore[attr-defined]
        result._has_subtitle = has_subtitle  # type: ignore[attr-defined]
        return result

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

        # ----- Title -----
        # MyMoviz uses h1 for English title, h1.movie-titlep for Persian page title
        # H1 typically looks like "Inception (2010)" for movies,
        # or "Breaking Bad (2008 –    )" for series (with end-year placeholder)
        h1 = soup.select_one("h1")
        if h1:
            h1_text = h1.get_text(" ", strip=True)
            # Try movie-style year first: "(2010)"
            year_match = re.search(r"\(\s*(\d{4})\s*\)", h1_text)
            if year_match:
                detail.year = int(year_match.group(1))
                detail.title_en = re.sub(r"\(\s*\d{4}\s*\)", "", h1_text).strip()
            else:
                # Try series-style year: "Breaking Bad (2008 –    )" -> 2008
                series_year_match = re.search(r"\(\s*(\d{4})\s*[–\-]", h1_text)
                if series_year_match:
                    detail.year = int(series_year_match.group(1))
                    # Strip the "(2008 –    )" part
                    detail.title_en = re.sub(
                        r"\(\s*\d{4}\s*[–\-][^)]*\)", "", h1_text
                    ).strip()
                else:
                    detail.title_en = h1_text

        # Persian title is in the <title> tag or h1.movie-titlep
        title_p = soup.select_one("h1.movie-titlep")
        if title_p:
            fa_text = title_p.get_text(" ", strip=True)
            # Strip "دانلود فیلم ... با دوبله فارسی" wrapper
            # Look for the title between "دانلود فیلم" and the year
            m = re.search(r"دانلود\s*(?:فیلم|سریال)\s+(.+?)\s+\d{4}", fa_text)
            if m:
                # The captured group may have both Persian and English - keep only Persian
                fa_part = m.group(1).strip()
                # Split into tokens and keep only Persian/CJK tokens
                tokens = fa_part.split()
                fa_tokens = [
                    tok for tok in tokens
                    if any(c.isalpha() and ord(c) > 0x0600 for c in tok)
                ]
                detail.title_fa = " ".join(fa_tokens) if fa_tokens else fa_part
            else:
                detail.title_fa = fa_text

        # If still no Persian title, try the page <title>
        if not detail.title_fa:
            page_title = soup.select_one("title")
            if page_title:
                t = page_title.get_text(strip=True)
                # Often "دانلود فیلم تلقین Inception 2010 با دوبله فارسی"
                m = re.search(r"دانلود\s*(?:فیلم|سریال)\s+([^\d]+?)\s+\d{4}", t)
                if m:
                    fa_part = m.group(1).strip()
                    # If it has both Persian and English, keep the Persian part
                    parts = fa_part.split()
                    fa_parts = [p for p in parts if any(c.isalpha() and ord(c) > 0x0600 for c in p)]
                    if fa_parts:
                        detail.title_fa = " ".join(fa_parts)

        # ----- Poster -----
        # Try og:image meta tag FIRST - it's the most reliable source for the
        # main poster. MyMoviz sets <meta property="og:image" content="..."/>
        # with the correct poster URL for this specific movie/series.
        poster_found = False
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image:
            content = og_image.get("content", "").strip()
            if content:
                content = content.replace("/./", "/")
                detail.poster_url = self._make_absolute_url(content)
                poster_found = True

        # Fallback: find poster in article with watchlist-loading-<id> class
        if not poster_found:
            # Extract imdb_id from URL (e.g. tt903747 from /tvshows/tt903747/...)
            imdb_id_match = re.search(r"(tt\d+)", url)
            if imdb_id_match:
                imdb_id = imdb_id_match.group(1)
                # Look for article with watchlist-loading-<imdb_id> class
                article_with_poster = soup.select_one(
                    f"article.-watchlist-loading-{imdb_id.lstrip('t')}, "
                    f"article[class*=-watchlist-loading-{imdb_id.lstrip('t')}]"
                )
                if article_with_poster:
                    img = article_with_poster.find("img")
                    if img:
                        src = img.get("data-src") or img.get("src")
                        if src:
                            src = src.replace("/./", "/")
                            detail.poster_url = self._make_absolute_url(src)
                            poster_found = True

        # Last resort: any img with "cover" in src (less reliable - may pick
        # a related movie's poster from the "similar movies" sidebar)
        if not poster_found:
            for img in soup.select("img[data-src]"):
                src = img.get("data-src") or img.get("src")
                if src and "cover" in src:
                    src = src.replace("/./", "/")
                    detail.poster_url = self._make_absolute_url(src)
                    break

        # ----- Summary -----
        # MyMoviz stores the summary in a specific section
        for el in soup.select(".movie-story, .story, .summary, .description, .plot, [class*=story], [class*=summary]"):
            text = el.get_text(" ", strip=True)
            if text and len(text) > 50:
                detail.summary = text
                break
        if not detail.summary:
            # Try the og:description meta tag
            meta_desc = soup.select_one('meta[name="description"], meta[property="og:description"]')
            if meta_desc:
                content = meta_desc.get("content", "").strip()
                if content and len(content) > 30:
                    detail.summary = content

        # ----- Genres (from -genre or m-genre links in the header only) -----
        # Restrict to inside article header to avoid sidebar/footer genre links
        header = soup.select_one("article.box-movie-details .box-movie-details-header, .box-movie-details-header")
        search_root = header if header else soup
        genre_links = search_root.select(".-genre a, .m-genre a, a[href*='/genres/']")
        if genre_links:
            genres = []
            for g in genre_links:
                t = g.get_text(strip=True)
                if t and t not in genres and "/genres/" in (g.get("href") or ""):
                    genres.append(t)
            if genres:
                detail.genres = ", ".join(genres[:8])

        # ----- Country -----
        for a in soup.select("a[href*='/countries/']"):
            t = a.get_text(strip=True)
            if t and len(t) < 50:
                detail.country = t
                break

        # ----- Duration -----
        text = soup.get_text(" ", strip=True)
        dur_match = re.search(r"(\d+\s*(?:ساعت|دقیقه|hour|min|h)(?:\s*\d+\s*دقیقه)?)", text)
        if dur_match:
            detail.duration = dur_match.group(1).strip()
        else:
            # Try mm:ss or h:mm format
            dur_match2 = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", text)
            if dur_match2:
                detail.duration = dur_match2.group(1)

        # ----- Year -----
        # Fallback: if year is None or unreasonable (e.g. > 2026 or < 1900),
        # try to extract from URL slug (e.g. /tt903747/Breaking-Bad-2008 -> 2008)
        if detail.year is None or detail.year > 2026 or detail.year < 1900:
            # Try URL first - most reliable
            url_year_match = re.search(r"-(\d{4})(?:$|/|\?)", url)
            if url_year_match:
                url_year = int(url_year_match.group(1))
                if 1900 <= url_year <= 2026:
                    detail.year = url_year
            # If still not found, try the page text
            if detail.year is None or detail.year > 2026 or detail.year < 1900:
                year_match = re.search(r"\(\s*(\d{4})\s*\)", text)
                if year_match:
                    candidate = int(year_match.group(1))
                    if 1900 <= candidate <= 2026:
                        detail.year = candidate

        # ----- IMDb rating -----
        # Rating is in div.-rating-rating with text like "8.8 /10 2114567 users"
        rating_el = soup.select_one("div.-rating-rating")
        if rating_el:
            rating_text = rating_el.get_text(" ", strip=True)
            # Extract just the first float (e.g. "8.8 /10 2114567 users" -> 8.8)
            m = re.search(r"(\d+\.\d+)", rating_text)
            if m:
                detail.imdb_rating = float(m.group(1))
        else:
            # Try other selectors
            for el in soup.select(".-rating-block, .movie-rating, .imdb-rating"):
                t = el.get_text(" ", strip=True)
                m = re.search(r"(\d+\.\d+)", t)
                if m:
                    detail.imdb_rating = float(m.group(1))
                    break

        # ----- Quality -----
        quality_el = soup.select_one(".-quality, .quality, .btn-quality")
        if quality_el:
            detail.qualities = quality_el.get_text(strip=True)
        else:
            # Search for quality text
            qs = []
            for q in soup.select("[class*=quality]"):
                t = q.get_text(strip=True)
                if t and t not in qs and len(t) < 50 and any(c.isdigit() or c.isalpha() for c in t):
                    qs.append(t)
            if qs:
                detail.qualities = ", ".join(dict.fromkeys(qs))

        # ----- Dubbing / Subtitle flags -----
        detail.has_dubbing = "دوبله" in text
        detail.has_subtitle = "زیرنویس" in text

        # ----- Download links (movie-style) -----
        detail.download_groups, detail.download_links = self._parse_movie_downloads(soup)

        # ----- Episodes (series) -----
        # Always try to parse episodes - if the page has them, it's a series.
        # We can't rely on the content_type parameter because the caller may
        # pass "movie" even for series URLs (e.g. when using /tt<ID> which
        # works for both).
        detail.episodes, detail.seasons = self._parse_episodes_with_downloads(soup)
        if detail.episodes:
            # This is actually a series (has episodes)
            detail.content_type = "series"
            ep = detail.episodes[0]
            detail.latest_episode = f"فصل {ep.season or '?'} قسمت {ep.episode or '?'}"

        # ----- Raw hash for change detection -----
        body_text = soup.get_text(" ", strip=True)
        detail.raw_hash = hashlib.md5(body_text.encode("utf-8")).hexdigest()[:16]

        return detail

    def _parse_movie_downloads(self, soup: BeautifulSoup) -> tuple[list, list]:
        """Parse movie download section into structured DownloadGroup objects.

        Returns (download_groups, flat_download_links).
        """
        from scrapers.base import DownloadGroup

        groups: list[DownloadGroup] = []
        flat_links: list[dict] = []

        # Find the actual download section (not the "watch online" one)
        # It's the section with id="download" or contains "لینک های دانلود"
        download_section = None
        for section in soup.select("section.box-movie-download"):
            h = section.select_one("h3, h4, .-title")
            if h:
                title_text = h.get_text(strip=True)
                if "لینک های دانلود" in title_text or "دانلود فیلم" in title_text:
                    download_section = section
                    break

        if not download_section:
            # Fallback: any download section
            download_section = soup.select_one("section#download, section.box-movie-download:last-child")
            if not download_section:
                return groups, flat_links

        # Find each quality group (-dl-item)
        for item in download_section.select(".-dl-item"):
            group = DownloadGroup()
            header = item.select_one(".-dl-item-header")
            if header:
                # Get quality (e.g. "BluRay 1080p")
                quality_el = header.select_one("b.-font-large, b")
                if quality_el:
                    group.quality = quality_el.get_text(strip=True)
                # Get format and size from bdi elements
                bdis = [b.get_text(strip=True) for b in header.select("bdi")]
                for bdi in bdis:
                    if "MP4" in bdi or "MKV" in bdi or "AVI" in bdi:
                        group.format = bdi
                    elif "مگابایت" in bdi or "گیگابایت" in bdi or "GB" in bdi or "MB" in bdi:
                        group.size = bdi

            # Detect type (dubbed vs original)
            item_classes = item.get("class", [])
            if "dub-box" in item_classes:
                group.dtype = "dub"
            else:
                group.dtype = "orig"

            # Find download links (skip watch online and subtitle toggle buttons)
            for a in item.select("a.-btn-dl"):
                href = a.get("href", "").strip()
                text = a.get_text(strip=True)
                if not href or href.startswith("#") or href.startswith("/watch/"):
                    continue
                # Skip subtitle toggle buttons (no href)
                if not a.get("href"):
                    continue
                abs_url = self._make_absolute_url(href)
                # Skip /panel/charge (premium-only) - but note it
                if "/panel/charge" in href:
                    group.links.append({"label": "ویژه (اکانت پرمیوم)", "url": abs_url, "premium": True})
                else:
                    label = "دانلود"
                    if "دوبله" in text or "Dub" in text:
                        label = "دانلود دوبله"
                    elif "زبان اصلی" in text:
                        label = "دانلود زبان اصلی"
                    group.links.append({"label": label, "url": abs_url, "premium": False})
                    flat_links.append({"label": label, "url": abs_url, "quality": group.quality})

            # Find subtitle links
            for a in item.select('a[href*="/subtitles/"]'):
                href = a.get("href", "").strip()
                text = a.get_text(strip=True)
                if href:
                    abs_url = self._make_absolute_url(href)
                    group.subtitles.append({"label": text, "url": abs_url})
                    flat_links.append({"label": f"زیرنویس - {text}", "url": abs_url, "quality": ""})

            if group.quality or group.links:
                groups.append(group)

        return groups, flat_links

    def _parse_episodes_with_downloads(self, soup: BeautifulSoup) -> tuple[list, list]:
        """Parse series episodes with download groups.

        Returns (episodes, seasons).
        episodes: list of EpisodeDetail with download_groups populated.
        seasons: list of {"season": int, "episodes": int, "label": str}.
        """
        from scrapers.base import DownloadGroup

        episodes: list = []
        seasons: list[dict] = []

        # Find episode divs
        ep_divs = soup.select(".-dlepisode")
        season_eps: dict[int, list] = {}

        for ep_div in ep_divs:
            ep = EpisodeDetail()
            title_el = ep_div.select_one(".-dl-title")
            if title_el:
                title_text = title_el.get_text(" ", strip=True)
                # Parse "فصل 1 ، قسمت 1"
                m = re.search(r"فصل\s*(\d+).*?قسمت\s*(\d+)", title_text)
                if m:
                    ep.season = int(m.group(1))
                    ep.episode = int(m.group(2))
                else:
                    m2 = re.search(r"S(\d+)E(\d+)", title_text)
                    if m2:
                        ep.season = int(m2.group(1))
                        ep.episode = int(m2.group(2))
                ep.title = title_text[:100]

            # Parse quality groups within this episode
            for item in ep_div.select(".-dl-items"):
                group = DownloadGroup()
                header = item.select_one(".-dl-item-header")
                if header:
                    bdis = [b.get_text(strip=True) for b in header.select("bdi")]
                    for bdi in bdis:
                        bdi_clean = bdi.strip()
                        if re.match(r"(BluRay|WEB-DL|WEBRip|HDTV|HDRip|CAM|DVDScr)\s*\d{3,4}p", bdi_clean, re.I) or \
                           re.match(r"\d{3,4}p", bdi_clean):
                            group.quality = bdi_clean
                        elif "MP4" in bdi_clean or "MKV" in bdi_clean:
                            group.format = bdi_clean
                        elif "مگابایت" in bdi_clean or "گیگابایت" in bdi_clean:
                            group.size = bdi_clean

                # Detect type
                item_classes = item.get("class", [])
                if "dub-box" in item_classes:
                    group.dtype = "dub"
                else:
                    group.dtype = "orig"

                # Find download links
                for a in item.select("a.-btn-dl"):
                    href = a.get("href", "").strip()
                    text = a.get_text(strip=True)
                    if not href or href.startswith("#") or href.startswith("/watch/"):
                        continue
                    abs_url = self._make_absolute_url(href)
                    if "/panel/charge" in href:
                        group.links.append({"label": "ویژه", "url": abs_url, "premium": True})
                    else:
                        label = f"S{ep.season}E{ep.episode}"
                        if group.dtype == "dub":
                            label += " دوبله"
                        group.links.append({"label": label, "url": abs_url, "premium": False})

                # Find subtitle links
                for a in item.select('a[href*="/subtitles/"]'):
                    href = a.get("href", "").strip()
                    text = a.get_text(strip=True)
                    if href:
                        abs_url = self._make_absolute_url(href)
                        group.subtitles.append({"label": text, "url": abs_url})

                if group.quality or group.links:
                    ep.download_groups.append(group)

            if ep.season is not None:
                if ep.season not in season_eps:
                    season_eps[ep.season] = []
                season_eps[ep.season].append(ep)
                episodes.append(ep)

        # Build seasons list
        for season_num in sorted(season_eps.keys()):
            eps = season_eps[season_num]
            seasons.append({
                "season": season_num,
                "episodes": len(eps),
                "label": f"فصل {season_num}",
            })

        # Sort episodes: latest first within each season
        episodes.sort(key=lambda e: (e.season or 0, e.episode or 0), reverse=True)
        return episodes, seasons

    def _extract_genres(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract genre list from genre links."""
        genre_links = soup.select(".m-genre a, .genres a, .movie-genres a")
        if not genre_links:
            return None
        genres = [g.get_text(strip=True) for g in genre_links if g.get_text(strip=True)]
        return ", ".join(genres) if genres else None

    def _extract_meta_table(self, soup: BeautifulSoup) -> dict:
        """Extract key-value metadata from the detail page."""
        meta: dict[str, Optional[str]] = {}

        # Try table rows
        for row in soup.select("table tr, .info-row, .meta-row, .detail-row li, ul.info li"):
            cells = row.find_all(["td", "th", "span", "div", "b", "strong"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(" ", strip=True)
                if key:
                    meta[key] = value

        # Try labeled rows
        for row in soup.select(".row, .meta-item, .info-item, .m-b-6, .bx"):
            label = row.select_one(".label, .key, .meta-label, .small, b, strong")
            value = row.select_one(".value, .meta-value, .bold, .text-blue")
            if label and value:
                key = label.get_text(strip=True).rstrip(":")
                # Skip if key is too long (probably not a real label)
                if key and len(key) < 30:
                    meta[key] = value.get_text(" ", strip=True)

        return meta

    def _parse_episodes(self, soup: BeautifulSoup) -> List[EpisodeDetail]:
        """Extract episode list from a series detail page."""
        episodes: List[EpisodeDetail] = []

        # MyMoviz typically lists episodes with season/episode numbers
        ep_els = soup.select(
            ".episode, .episode-item, .episodes li, .episode-list .item, "
            "tr.episode, [class*=episode], .season-episode, .ep-row"
        )
        for ep_el in ep_els:
            ep = EpisodeDetail()
            text = ep_el.get_text(" ", strip=True)

            # Try to extract season/episode numbers from various formats
            m = re.search(r"(?:فصل|S|Season)\s*(\d+)\s*(?:قسمت|E|Episode)\s*(\d+)", text, re.I)
            if m:
                ep.season = int(m.group(1))
                ep.episode = int(m.group(2))
            else:
                m2 = re.search(r"S(\d+)E(\d+)", text, re.I)
                if m2:
                    ep.season = int(m2.group(1))
                    ep.episode = int(m2.group(2))
                else:
                    m3 = re.search(r"قسمت\s*(\d+)", text)
                    if m3:
                        ep.episode = int(m3.group(1))
                        ep.season = 1

            link = ep_el.find("a", href=True)
            if link:
                ep.page_url = self._make_absolute_url(link["href"])

            qualities = ep_el.select(".quality, [class*=quality]")
            if qualities:
                ep.qualities = ", ".join(
                    q.get_text(strip=True) for q in qualities if q.get_text(strip=True)
                )

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
