"""
Unit tests for the scrapers package - parsing helpers, fallback logic.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from scrapers.classic import ClassicScraper
from scrapers.modern import ModernScraper
from scrapers.base import BaseScraper


class TestBaseScraperHelpers:
    """Test static helpers on the BaseScraper."""

    def test_safe_int_valid(self) -> None:
        assert BaseScraper._safe_int("2024") == 2024
        assert BaseScraper._safe_int("  ۱۳۹۰  ") is None  # Persian digits

    def test_safe_int_invalid(self) -> None:
        assert BaseScraper._safe_int(None) is None
        assert BaseScraper._safe_int("") is None
        assert BaseScraper._safe_int("abc") is None

    def test_safe_float_valid(self) -> None:
        assert BaseScraper._safe_float("8.5") == 8.5
        assert BaseScraper._safe_float("8,5") == 8.5  # comma decimal
        assert BaseScraper._safe_float("  7.2  ") == 7.2

    def test_safe_float_invalid(self) -> None:
        assert BaseScraper._safe_float(None) is None
        assert BaseScraper._safe_float("abc") is None


class TestClassicScraperParsing:
    """Test that the classic scraper can parse sample HTML fragments."""

    def test_parse_card_grid_basic(self) -> None:
        html = """
        <div>
          <div class="movie-card">
            <a href="/movie/123-test"><img src="/posters/123.jpg"/></a>
            <h3 class="title">تست فیلم</h3>
            <span class="title-en">Test Movie</span>
            <span class="year">2023</span>
            <span class="imdb">8.5</span>
          </div>
          <div class="movie-card">
            <a href="/series/456-test"><img src="/posters/456.jpg"/></a>
            <h3 class="title">تست سریال</h3>
            <span class="year">2024</span>
          </div>
        </div>
        """
        scraper = ClassicScraper()
        soup = BeautifulSoup(html, "lxml")
        results = scraper._parse_card_grid(soup)
        assert len(results) == 2
        assert results[0].content_type == "movie"
        assert results[0].title_fa == "تست فیلم"
        assert results[0].title_en == "Test Movie"
        assert results[0].year == 2023
        assert results[0].imdb_rating == 8.5
        assert results[0].mymoviz_id == "123-test"
        assert results[1].content_type == "series"

    def test_parse_card_grid_empty(self) -> None:
        scraper = ClassicScraper()
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        assert scraper._parse_card_grid(soup) == []

    def test_make_absolute_url(self) -> None:
        scraper = ClassicScraper()
        assert scraper._make_absolute_url("/movie/1").startswith("https://")
        assert scraper._make_absolute_url("https://x.com/y") == "https://x.com/y"
        assert scraper._make_absolute_url(None) is None
        assert scraper._make_absolute_url("//cdn.test/x.jpg").startswith("https://")


class TestModernScraperParsing:
    """Test that the modern scraper can parse SPA-style HTML fragments."""

    def test_parse_modern_card_with_data_attrs(self) -> None:
        html = """
        <div class="movie-card" data-title="فیلم نمونه" data-title-en="Sample"
             data-year="2024" data-rating="9.0" data-poster="/p.jpg">
          <a href="/_modern/movie/999-slug"></a>
        </div>
        """
        scraper = ModernScraper()
        soup = BeautifulSoup(html, "lxml")
        results = scraper._parse_modern_grid(soup)
        assert len(results) == 1
        r = results[0]
        assert r.title_fa == "فیلم نمونه"
        assert r.title_en == "Sample"
        assert r.year == 2024
        assert r.imdb_rating == 9.0
        assert r.mymoviz_id == "999-slug"
        assert r.content_type == "movie"

    def test_parse_modern_episodes_regex(self) -> None:
        html = """
        <div class="episode-item" data-season="2" data-episode="5">
          <a href="/_modern/series/x/s2e5">لینک</a>
        </div>
        """
        scraper = ModernScraper()
        soup = BeautifulSoup(html, "lxml")
        eps = scraper._parse_modern_episodes(soup)
        assert len(eps) == 1
        assert eps[0].season == 2
        assert eps[0].episode == 5
