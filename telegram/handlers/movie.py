"""
Movie/Series detail handlers - show full info, download flow (season→quality→links),
favorite/subscription actions.

Uses short IMDb IDs (without "tt" prefix) in callback_data:
    d:<id>       → detail page
    fav:<id>     → toggle favorite
    sub:<id>     → toggle subscription
    dl:<id>      → download (movies: show qualities, series: show seasons)
    sq:<id>:<s>  → season <s> quality selection (series only)
    ql:<id>:<s>:<quality> → show all download links for quality <quality> in season <s>
"""

from __future__ import annotations

from typing import Optional

from aiogram import Router
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from cache.cache_manager import cache
from database.models import ContentType, User
from database.repositories import (
    FavoriteRepository,
    MovieRepository,
    SeriesRepository,
    SubscriptionRepository,
)
from scrapers.manager import scraper_manager
from telegram.keyboards import (
    back_to_main_kb,
    content_detail_kb,
    resolve_short_id,
    seasons_kb,
    qualities_kb,
)
from telegram.safe_edit import safe_edit_message, safe_delete_message
from utils.formatters import format_movie_info, format_series_info
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="movie")


# ----------------------------------------------------------------------
# Detail callback: d:<short_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("d:"))
async def cb_detail(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Open the detail page for a movie or series."""
    short_id = callback.data[2:]
    imdb_id = resolve_short_id(short_id)  # e.g. "tt1375666"

    # Check cache first
    cache_key = f"detail:{imdb_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Detail cache hit for {}", cache_key)
        await _render_detail(callback.message, cached, imdb_id, db_user, session)
        await callback.answer()
        return

    await safe_edit_message(callback.message, "⏳ در حال دریافت اطلاعات...")

    # Fetch detail page using just the IMDb ID (works for both movies and series)
    detail = await scraper_manager.get_content_detail(imdb_id, "movie")
    if not detail:
        # Try as series
        detail = await scraper_manager.get_content_detail(imdb_id, "series")

    if not detail:
        await safe_edit_message(
            callback.message,
            "❌ اطلاعات این مورد دریافت نشد. ممکن است حذف شده باشد.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    # Determine content type from URL or episodes
    if detail.page_url and "/tvshows/" in detail.page_url:
        content_type_str = "series"
    elif detail.episodes:
        content_type_str = "series"
    else:
        content_type_str = "movie"
    content_type = ContentType.SERIES if content_type_str == "series" else ContentType.MOVIE
    detail.content_type = content_type_str

    # Persist to database
    data = {
        "mymoviz_id": detail.mymoviz_id or imdb_id,
        "title_fa": detail.title_fa,
        "title_en": detail.title_en,
        "year": detail.year,
        "imdb_rating": detail.imdb_rating,
        "poster_url": detail.poster_url,
        "page_url": detail.page_url,
        "summary": detail.summary,
        "genres": detail.genres,
        "country": detail.country,
        "duration": detail.duration,
        "qualities": detail.qualities,
        "has_dubbing": detail.has_dubbing,
        "has_subtitle": detail.has_subtitle,
        "latest_episode": detail.latest_episode,
        "raw_hash": detail.raw_hash,
    }
    if content_type == ContentType.MOVIE:
        movie = await MovieRepository.upsert(session, data)
        db_id = movie.id
    else:
        series = await SeriesRepository.upsert(session, data)
        db_id = series.id

    payload = {
        "detail": {
            "title_fa": detail.title_fa,
            "title_en": detail.title_en,
            "year": detail.year,
            "imdb_rating": detail.imdb_rating,
            "poster_url": detail.poster_url,
            "page_url": detail.page_url,
            "summary": detail.summary,
            "genres": detail.genres,
            "country": detail.country,
            "duration": detail.duration,
            "qualities": detail.qualities,
            "has_dubbing": detail.has_dubbing,
            "has_subtitle": detail.has_subtitle,
            "latest_episode": detail.latest_episode,
            "content_type": content_type_str,
            "mymoviz_id": detail.mymoviz_id or imdb_id,
            "db_id": db_id,
        },
        "download_groups": [
            {
                "quality": g.quality,
                "format": g.format,
                "size": g.size,
                "dtype": g.dtype,
                "links": g.links,
                "subtitles": g.subtitles,
            }
            for g in detail.download_groups
        ],
        "seasons": detail.seasons,
        "episodes": [
            {
                "season": e.season,
                "episode": e.episode,
                "title": e.title,
                "download_groups": [
                    {
                        "quality": g.quality,
                        "format": g.format,
                        "size": g.size,
                        "dtype": g.dtype,
                        "links": g.links,
                        "subtitles": g.subtitles,
                    }
                    for g in e.download_groups
                ],
            }
            for e in detail.episodes
        ],
    }
    await cache.set(cache_key, payload)
    await _render_detail(callback.message, payload, imdb_id, db_user, session)
    await callback.answer()


async def _render_detail(
    message: Message,
    payload: dict,
    imdb_id: str,
    db_user: User,
    session: AsyncSession,
) -> None:
    """Render the detail message with poster + buttons."""
    d = payload["detail"]
    content_type_str = d.get("content_type", "movie")
    content_type = ContentType.SERIES if content_type_str == "series" else ContentType.MOVIE

    # Build text
    if content_type == ContentType.MOVIE:
        class _M:
            pass
        m = _M()
        for k, v in d.items():
            setattr(m, k, v)
        text = format_movie_info(m)
    else:
        class _S:
            pass
        s = _S()
        for k, v in d.items():
            setattr(s, k, v)
        text = format_series_info(s)

    # Check favorite & subscription status
    db_id = d.get("db_id")
    is_fav = False
    is_sub = False
    if db_id and db_user:
        is_fav = await FavoriteRepository.exists(
            session, db_user.id, content_type,
            movie_id=db_id if content_type == ContentType.MOVIE else None,
            series_id=db_id if content_type == ContentType.SERIES else None,
        )
        is_sub = await SubscriptionRepository.exists(
            session, db_user.id, content_type,
            movie_id=db_id if content_type == ContentType.MOVIE else None,
            series_id=db_id if content_type == ContentType.SERIES else None,
        )

    kb = content_detail_kb(
        content_type=content_type,
        mymoviz_id=imdb_id,
        site_url=d.get("page_url"),
        is_favorite=is_fav,
        is_subscribed=is_sub,
    )

    poster_url = d.get("poster_url")
    if poster_url:
        if message.photo:
            try:
                await message.edit_caption(caption=text, reply_markup=kb)
            except Exception as exc:
                logger.warning("edit_caption failed: {}", exc)
                await safe_edit_message(message, text, reply_markup=kb)
        else:
            await safe_delete_message(message)
            try:
                await message.answer_photo(photo=poster_url, caption=text, reply_markup=kb)
            except Exception as exc:
                logger.warning("answer_photo failed: {}", exc)
                await message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await safe_edit_message(message, text, reply_markup=kb)


# ----------------------------------------------------------------------
# Favorite callback: fav:<short_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("fav:"))
async def cb_favorite(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Toggle favorite status for a content item."""
    short_id = callback.data[4:]
    imdb_id = resolve_short_id(short_id)

    # Try movie first, then series
    movie = await MovieRepository.get_by_mymoviz_id(session, imdb_id)
    if movie:
        content_type = ContentType.MOVIE
        exists = await FavoriteRepository.exists(session, db_user.id, content_type, movie_id=movie.id)
        if exists:
            await FavoriteRepository.remove(session, db_user.id, content_type, movie_id=movie.id)
            await callback.answer("❌ از علاقه‌مندی حذف شد.")
        else:
            await FavoriteRepository.add(session, db_user.id, content_type, movie_id=movie.id)
            await callback.answer("⭐ به علاقه‌مندی اضافه شد.")
        return

    series = await SeriesRepository.get_by_mymoviz_id(session, imdb_id)
    if series:
        content_type = ContentType.SERIES
        exists = await FavoriteRepository.exists(session, db_user.id, content_type, series_id=series.id)
        if exists:
            await FavoriteRepository.remove(session, db_user.id, content_type, series_id=series.id)
            await callback.answer("❌ از علاقه‌مندی حذف شد.")
        else:
            await FavoriteRepository.add(session, db_user.id, content_type, series_id=series.id)
            await callback.answer("⭐ به علاقه‌مندی اضافه شد.")
        return

    await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)


# ----------------------------------------------------------------------
# Subscription callback: sub:<short_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("sub:"))
async def cb_subscribe(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Toggle subscription for a content item."""
    short_id = callback.data[4:]
    imdb_id = resolve_short_id(short_id)

    movie = await MovieRepository.get_by_mymoviz_id(session, imdb_id)
    if movie:
        now_active = await SubscriptionRepository.toggle(
            session, db_user.id, ContentType.MOVIE, movie_id=movie.id
        )
        msg = "🔔 اطلاع‌رسانی فعال شد." if now_active else "❌ اطلاع‌رسانی غیرفعال شد."
        await callback.answer(msg)
        return

    series = await SeriesRepository.get_by_mymoviz_id(session, imdb_id)
    if series:
        now_active = await SubscriptionRepository.toggle(
            session, db_user.id, ContentType.SERIES, series_id=series.id
        )
        msg = "🔔 اطلاع‌رسانی فعال شد." if now_active else "❌ اطلاع‌رسانی غیرفعال شد."
        await callback.answer(msg)
        return

    await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)


# ----------------------------------------------------------------------
# Favorites list: favorites:list
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "favorites:list")
async def cb_favorites_list(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Show the user's favorite list."""
    from telegram.keyboards import favorites_list_kb
    favs = await FavoriteRepository.list_by_user(session, db_user.id)
    if not favs:
        await safe_edit_message(
            callback.message,
            "⭐ هنوز هیچ علاقه‌مندی‌ای ثبت نکرده‌اید.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    items: list[dict] = []
    for fav in favs:
        if fav.content_type == ContentType.MOVIE and fav.movie:
            items.append({
                "content_type": "movie",
                "mymoviz_id": fav.movie.mymoviz_id,
                "title": fav.movie.title_fa or fav.movie.title_en or "—",
            })
        elif fav.content_type == ContentType.SERIES and fav.series:
            items.append({
                "content_type": "series",
                "mymoviz_id": fav.series.mymoviz_id,
                "title": fav.series.title_fa or fav.series.title_en or "—",
            })
    await safe_edit_message(
        callback.message,
        f"⭐ <b>علاقه‌مندی‌های شما ({len(items)})</b>",
        reply_markup=favorites_list_kb(items),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Subscriptions list: subscriptions:list
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "subscriptions:list")
async def cb_subscriptions_list(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Show the user's active subscriptions."""
    from telegram.keyboards import subscriptions_list_kb
    subs = await SubscriptionRepository.list_by_user(session, db_user.id)
    active = [s for s in subs if s.is_active]
    if not active:
        await safe_edit_message(
            callback.message, "🔔 هیچ اعلان فعالی ندارید.", reply_markup=back_to_main_kb()
        )
        await callback.answer()
        return

    items: list[dict] = []
    for sub in active:
        if sub.content_type == ContentType.MOVIE and sub.movie:
            items.append({
                "content_type": "movie",
                "mymoviz_id": sub.movie.mymoviz_id,
                "title": sub.movie.title_fa or sub.movie.title_en or "—",
            })
        elif sub.content_type == ContentType.SERIES and sub.series:
            items.append({
                "content_type": "series",
                "mymoviz_id": sub.series.mymoviz_id,
                "title": sub.series.title_fa or sub.series.title_en or "—",
            })
    await safe_edit_message(
        callback.message,
        f"🔔 <b>اعلان‌های فعال شما ({len(items)})</b>",
        reply_markup=subscriptions_list_kb(items),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Download flow: dl:<short_id>
# For movies: show quality buttons
# For series: show season buttons
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("dl:"))
async def cb_download(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show download options - movies: qualities, series: seasons."""
    short_id = callback.data[3:]
    imdb_id = resolve_short_id(short_id)

    # Check cache for detail data
    cache_key = f"detail:{imdb_id}"
    cached = await cache.get(cache_key)
    if not cached:
        # Need to fetch detail first
        await safe_edit_message(callback.message, "⏳ در حال دریافت اطلاعات...")
        # Trigger detail fetch by calling the detail handler logic
        # For simplicity, just show a message
        await safe_edit_message(
            callback.message,
            "❌ ابتدا صفحه اطلاعات را باز کنید، بعد دانلود را بزنید.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    d = cached["detail"]
    content_type_str = d.get("content_type", "movie")
    title = d.get("title_fa") or d.get("title_en") or "—"

    if content_type_str == "series":
        # Show seasons
        seasons = cached.get("seasons", [])
        if not seasons:
            await safe_edit_message(
                callback.message,
                f"📺 <b>{title}</b>\n\n❌ قسمتی برای این سریال یافت نشد.",
                reply_markup=back_to_main_kb(),
            )
            await callback.answer()
            return
        await safe_edit_message(
            callback.message,
            f"📺 <b>{title}</b>\n\n📋 یک فصل را برای دانلود انتخاب کنید:",
            reply_markup=seasons_kb(short_id, seasons),
        )
    else:
        # Movie: show qualities
        download_groups = cached.get("download_groups", [])
        if not download_groups:
            await safe_edit_message(
                callback.message,
                f"🎬 <b>{title}</b>\n\n❌ لینک دانلودی برای این فیلم یافت نشد.",
                reply_markup=back_to_main_kb(),
            )
            await callback.answer()
            return
        # Build quality list
        qualities = []
        for g in download_groups:
            qualities.append({
                "quality": g.get("quality", ""),
                "size": g.get("size", ""),
                "type": g.get("dtype", ""),
            })
        await safe_edit_message(
            callback.message,
            f"🎬 <b>{title}</b>\n\n🎥 یک کیفیت را برای دانلود انتخاب کنید:",
            reply_markup=qualities_kb(short_id, None, qualities),
        )
    await callback.answer()


# ----------------------------------------------------------------------
# Season quality selection: sq:<short_id>:<season>
# Series only - show qualities for a specific season
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("sq:"))
async def cb_season_quality(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show quality options for a specific season."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    short_id = parts[1]
    season_num = int(parts[2])
    imdb_id = resolve_short_id(short_id)

    cache_key = f"detail:{imdb_id}"
    cached = await cache.get(cache_key)
    if not cached:
        await safe_edit_message(callback.message, "❌ نشست منقضی شده. دوباره باز کنید.", reply_markup=back_to_main_kb())
        await callback.answer()
        return

    d = cached["detail"]
    title = d.get("title_fa") or d.get("title_en") or "—"
    episodes = cached.get("episodes", [])

    # Filter episodes for this season
    season_eps = [e for e in episodes if e.get("season") == season_num]
    if not season_eps:
        await safe_edit_message(callback.message, "❌ قسمتی برای این فصل یافت نشد.", reply_markup=back_to_main_kb())
        await callback.answer()
        return

    # Collect all unique qualities for this season
    qualities_map: dict[str, dict] = {}
    for ep in season_eps:
        for g in ep.get("download_groups", []):
            q = g.get("quality", "")
            if q and q not in qualities_map:
                qualities_map[q] = {
                    "quality": q,
                    "size": g.get("size", ""),
                    "type": g.get("dtype", ""),
                }

    qualities = list(qualities_map.values())
    if not qualities:
        await safe_edit_message(callback.message, "❌ کیفیتی برای این فصل یافت نشد.", reply_markup=back_to_main_kb())
        await callback.answer()
        return

    await safe_edit_message(
        callback.message,
        f"📺 <b>{title}</b> - فصل {season_num}\n\n🎥 یک کیفیت را انتخاب کنید:",
        reply_markup=qualities_kb(short_id, season_num, qualities),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Quality links: ql:<short_id>:<season>:<quality>
# Show all download links for a specific quality (and season for series)
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("ql:"))
async def cb_quality_links(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show all download links for a specific quality."""
    parts = callback.data.split(":", 3)
    if len(parts) < 4:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    short_id = parts[1]
    season_num = int(parts[2])
    quality = parts[3]
    imdb_id = resolve_short_id(short_id)

    cache_key = f"detail:{imdb_id}"
    cached = await cache.get(cache_key)
    if not cached:
        await safe_edit_message(callback.message, "❌ نشست منقضی شده.", reply_markup=back_to_main_kb())
        await callback.answer()
        return

    d = cached["detail"]
    title = d.get("title_fa") or d.get("title_en") or "—"
    content_type_str = d.get("content_type", "movie")

    builder = InlineKeyboardBuilder()
    text_lines = []

    if season_num > 0 and content_type_str == "series":
        # Series: collect all links for this season + quality
        episodes = cached.get("episodes", [])
        season_eps = [e for e in episodes if e.get("season") == season_num]
        # Sort by episode number ascending
        season_eps.sort(key=lambda e: e.get("episode", 0))

        text_lines.append(f"📺 <b>{title}</b> - فصل {season_num} - {quality}\n")
        text_lines.append(f"📥 تعداد قسمت‌ها: {len(season_eps)}\n")

        # Collect all download links and subtitles
        all_links: list[dict] = []
        all_subs: list[dict] = []
        for ep in season_eps:
            for g in ep.get("download_groups", []):
                if g.get("quality", "") == quality:
                    for link in g.get("links", []):
                        if not link.get("premium"):
                            all_links.append({
                                "label": f"S{ep['season']}E{ep['episode']}",
                                "url": link["url"],
                            })
                    for sub in g.get("subtitles", []):
                        all_subs.append({
                            "label": f"S{ep['season']}E{ep['episode']} - {sub['label']}",
                            "url": sub["url"],
                        })

        if all_links:
            text_lines.append(f"\n📥 <b>لینک‌های دانلود ({len(all_links)}):</b>")
            for link in all_links:
                builder.add(InlineKeyboardButton(
                    text=f"📥 {link['label']}"[:50],
                    url=link["url"],
                ))

        if all_subs:
            text_lines.append(f"\n📝 <b>زیرنویس‌ها ({len(all_subs)}):</b>")
            for sub in all_subs[:10]:
                builder.add(InlineKeyboardButton(
                    text=f"📝 {sub['label']}"[:50],
                    url=sub["url"],
                ))

        builder.adjust(1)
        builder.add(InlineKeyboardButton(text="⬅ بازگشت به فصل‌ها", callback_data=f"dl:{short_id}"))
    else:
        # Movie: show links for this quality
        download_groups = cached.get("download_groups", [])
        text_lines.append(f"🎬 <b>{title}</b> - {quality}\n")

        all_links: list[dict] = []
        all_subs: list[dict] = []
        for g in download_groups:
            if g.get("quality", "") == quality:
                for link in g.get("links", []):
                    if not link.get("premium"):
                        all_links.append({"label": "دانلود", "url": link["url"]})
                for sub in g.get("subtitles", []):
                    all_subs.append({"label": sub["label"], "url": sub["url"]})

        if all_links:
            text_lines.append(f"\n📥 <b>لینک‌های دانلود ({len(all_links)}):</b>")
            for link in all_links:
                builder.add(InlineKeyboardButton(
                    text=f"📥 {link['label']}"[:50],
                    url=link["url"],
                ))

        if all_subs:
            text_lines.append(f"\n📝 <b>زیرنویس‌ها ({len(all_subs)}):</b>")
            for sub in all_subs:
                builder.add(InlineKeyboardButton(
                    text=f"📝 {sub['label']}"[:50],
                    url=sub["url"],
                ))

        builder.adjust(1)
        builder.add(InlineKeyboardButton(text="⬅ بازگشت به کیفیت‌ها", callback_data=f"dl:{short_id}"))

    builder.add(InlineKeyboardButton(text="🏠 خانه", callback_data="menu:main"))

    text = "\n".join(text_lines)[:4000]
    if not all_links and not all_subs:
        text += "\n\n⚠ لینک دانلود رایگان برای این کیفیت موجود نیست.\nممکن است نیاز به اکانت ویژه داشته باشد."

    await safe_edit_message(callback.message, text, reply_markup=builder.as_markup())
    await callback.answer()
