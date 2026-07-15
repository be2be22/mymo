"""
Listing handlers - movies, series, latest, popular.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from cache.cache_manager import cache
from database.models import User
from scrapers.manager import scraper_manager
from telegram.keyboards import search_results_kb, back_to_main_kb
from utils.formatters import format_search_result
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="listings")


async def _show_listing(
    callback: CallbackQuery,
    items: list[dict],
    title: str,
    cache_key: str,
) -> None:
    """Render a generic listing."""
    if not items:
        await callback.message.edit_text(
            f"🔍 {title}یافت نشد.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    lines = [f"📋 <b>{title}</b>\n"]
    for idx, item in enumerate(items, start=1):
        lines.append(f"<b>{idx}.</b> " + format_search_result(item))
        lines.append("➖➖➖➖➖➖➖➖➖➖")
    text = "\n".join(lines)[:4000]
    await cache.set(cache_key, items)
    await callback.message.edit_text(
        text, reply_markup=search_results_kb(items), disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "list:movies")
async def cb_list_movies(callback: CallbackQuery) -> None:
    """Show latest movies."""
    cache_key = "list:movies"
    cached = await cache.get(cache_key)
    if cached:
        await _show_listing(callback, cached, "🎬 فیلم‌های اخیر - ", cache_key)
        return
    try:
        results = await scraper_manager.get_latest_movies(limit=15)
    except Exception as exc:
        logger.error("list movies failed: {}", exc)
        await callback.message.edit_text(
            "❌ خطا در دریافت فهرست فیلم‌ها.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    items = [
        {
            "title_fa": r.title_fa,
            "title_en": r.title_en,
            "year": r.year,
            "imdb_rating": r.imdb_rating,
            "content_type": r.content_type,
            "poster_url": r.poster_url,
            "page_url": r.page_url,
            "mymoviz_id": r.mymoviz_id,
        }
        for r in results
    ]
    await _show_listing(callback, items, "🎬 فیلم‌های اخیر - ", cache_key)


@router.callback_query(lambda c: c.data == "list:series")
async def cb_list_series(callback: CallbackQuery) -> None:
    """Show latest series."""
    cache_key = "list:series"
    cached = await cache.get(cache_key)
    if cached:
        await _show_listing(callback, cached, "📺 سریال‌های اخیر - ", cache_key)
        return
    try:
        results = await scraper_manager.get_latest_series(limit=15)
    except Exception as exc:
        logger.error("list series failed: {}", exc)
        await callback.message.edit_text(
            "❌ خطا در دریافت فهرست سریال‌ها.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    items = [
        {
            "title_fa": r.title_fa,
            "title_en": r.title_en,
            "year": r.year,
            "imdb_rating": r.imdb_rating,
            "content_type": r.content_type,
            "poster_url": r.poster_url,
            "page_url": r.page_url,
            "mymoviz_id": r.mymoviz_id,
        }
        for r in results
    ]
    await _show_listing(callback, items, "📺 سریال‌های اخیر - ", cache_key)


@router.callback_query(lambda c: c.data == "list:latest")
async def cb_list_latest(callback: CallbackQuery) -> None:
    """Show latest releases (combined movies + series)."""
    cache_key = "list:latest"
    cached = await cache.get(cache_key)
    if cached:
        await _show_listing(callback, cached, "🕒 آخرین انتشارها - ", cache_key)
        return
    try:
        movies = await scraper_manager.get_latest_movies(limit=10)
        series = await scraper_manager.get_latest_series(limit=10)
    except Exception as exc:
        logger.error("list latest failed: {}", exc)
        await callback.message.edit_text(
            "❌ خطا در دریافت آخرین انتشارها.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    results = movies + series
    items = [
        {
            "title_fa": r.title_fa,
            "title_en": r.title_en,
            "year": r.year,
            "imdb_rating": r.imdb_rating,
            "content_type": r.content_type,
            "poster_url": r.poster_url,
            "page_url": r.page_url,
            "mymoviz_id": r.mymoviz_id,
        }
        for r in results
    ]
    await _show_listing(callback, items, "🕒 آخرین انتشارها - ", cache_key)


@router.callback_query(lambda c: c.data == "list:popular")
async def cb_list_popular(callback: CallbackQuery) -> None:
    """Show popular content."""
    cache_key = "list:popular"
    cached = await cache.get(cache_key)
    if cached:
        await _show_listing(callback, cached, "🔥 محبوب‌ترین‌ها - ", cache_key)
        return
    try:
        results = await scraper_manager.get_popular(limit=15)
    except Exception as exc:
        logger.error("list popular failed: {}", exc)
        await callback.message.edit_text(
            "❌ خطا در دریافت محبوب‌ترین‌ها.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    items = [
        {
            "title_fa": r.title_fa,
            "title_en": r.title_en,
            "year": r.year,
            "imdb_rating": r.imdb_rating,
            "content_type": r.content_type,
            "poster_url": r.poster_url,
            "page_url": r.page_url,
            "mymoviz_id": r.mymoviz_id,
        }
        for r in results
    ]
    await _show_listing(callback, items, "🔥 محبوب‌ترین‌ها - ", cache_key)


@router.callback_query(lambda c: c.data == "downloads:status")
async def cb_downloads_status(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Show downloads status (placeholder: list user subscriptions)."""
    from database.models import ContentType
    from database.repositories import SubscriptionRepository

    subs = await SubscriptionRepository.list_by_user(session, db_user.id)
    active = [s for s in subs if s.is_active]
    if not active:
        await callback.message.edit_text(
            "📊 <b>وضعیت دانلودها</b>\n\n"
            "شما هیچ اعلان فعالی ندارید.\n"
            "برای دنبال کردن وضعیت یک فیلم یا سریال، از صفحه آن گزینه «🔔 اطلاع بده» را بزنید.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return
    text_lines = [
        "📊 <b>وضعیت دانلودها</b>",
        "",
        f"🔔 تعداد اعلان‌های فعال: {len(active)}",
        "",
    ]
    for sub in active:
        if sub.content_type == ContentType.MOVIE and sub.movie:
            title = sub.movie.title_fa or sub.movie.title_en or "—"
            text_lines.append(f"🎬 {title}")
        elif sub.content_type == ContentType.SERIES and sub.series:
            title = sub.series.title_fa or sub.series.title_en or "—"
            text_lines.append(f"📺 {title}")
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()
