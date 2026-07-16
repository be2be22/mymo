"""
Quick standalone test of the ClassicScraper against the real MyMoviz site.
Run from inside the project directory:

    python tests/test_live_scrape.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.client import http_client
from scrapers.classic import ClassicScraper
from scrapers.manager import scraper_manager


async def main() -> None:
    print("=== Initializing HTTP client ===")
    await http_client.init()

    print("=== Attempting MyMoviz login ===")
    ok = await http_client.login_to_mymoviz()
    print(f"Login result: {ok}")

    print("\n=== Testing ClassicScraper.search('inception') ===")
    scraper = ClassicScraper()
    results = await scraper.search("inception")
    print(f"Got {len(results)} results")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.title_fa or r.title_en} ({r.year}) - IMDb: {r.imdb_rating}")
        print(f"     type={r.content_type}, mymoviz_id={r.mymoviz_id}")
        print(f"     poster={r.poster_url}")
        print(f"     page={r.page_url}")

    if results:
        print(f"\n=== Testing detail page for first result: {results[0].mymoviz_id} ===")
        detail = await scraper.get_content_detail(
            results[0].mymoviz_id, results[0].content_type
        )
        if detail:
            print(f"  title_fa: {detail.title_fa}")
            print(f"  title_en: {detail.title_en}")
            print(f"  year: {detail.year}")
            print(f"  imdb: {detail.imdb_rating}")
            print(f"  genres: {detail.genres}")
            print(f"  country: {detail.country}")
            print(f"  duration: {detail.duration}")
            print(f"  qualities: {detail.qualities}")
            print(f"  has_dubbing: {detail.has_dubbing}")
            print(f"  has_subtitle: {detail.has_subtitle}")
            print(f"  summary: {(detail.summary or '')[:200]}")
            print(f"  episodes: {len(detail.episodes)}")
            print(f"  raw_hash: {detail.raw_hash}")
        else:
            print("  ❌ Detail not parsed!")

    print("\n=== Testing ScraperManager.search('avengers') ===")
    results2 = await scraper_manager.search("avengers")
    print(f"Got {len(results2)} results")
    for i, r in enumerate(results2[:3], 1):
        print(f"  {i}. {r.title_fa or r.title_en} ({r.year}) - IMDb: {r.imdb_rating}")

    await http_client.close()
    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
