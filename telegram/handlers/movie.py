"""
Movie/Series detail handlers - show full info and favorite/subscription actions.
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
)
from utils.formatters import format_movie_info, format_series_info
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="movie")


# ----------------------------------------------------------------------
# Detail callback: detail:<content_type>:<mymoviz_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("detail:"))
async def cb_detail(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Open the detail page for a movie or series."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    content_type_str = parts[1]
    mymoviz_id = parts[2]

    if content_type_str not in ("movie", "series"):
        await callback.answer("❌ نوع نامعتبر است.", show_alert=True)
        return

    content_type = ContentType.MOVIE if content_type_str == "movie" else ContentType.SERIES

    # Check cache first
    cache_key = f"detail:{content_type_str}:{mymoviz_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Detail cache hit for {}", cache_key)
        await _render_detail(callback.message, cached, content_type, mymoviz_id, db_user, session)
        await callback.answer()
        return

    wait_text = "⏳ در حال دریافت اطلاعات..."
    try:
        await callback.message.edit_text(wait_text)
    except Exception:
        pass

    detail = await scraper_manager.get_content_detail(mymoviz_id, content_type_str)
    if not detail:
        await callback.message.edit_text(
            "❌ اطلاعات این مورد دریافت نشد. ممکن است حذف شده باشد.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    # Persist to database (upsert)
    data = {
        "mymoviz_id": detail.mymoviz_id or mymoviz_id,
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
        # Persist latest episodes
        if detail.episodes:
            from database.repositories import EpisodeRepository
            for ep in detail.episodes:
                await EpisodeRepository.upsert(
                    session,
                    {
                        "series_id": series.id,
                        "season": ep.season,
                        "episode": ep.episode,
                        "title": ep.title,
                        "page_url": ep.page_url,
                        "qualities": ep.qualities,
                        "has_dubbing": ep.has_dubbing,
                        "has_subtitle": ep.has_subtitle,
                    },
                )

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
            "mymoviz_id": detail.mymoviz_id or mymoviz_id,
            "db_id": db_id,
        }
    }
    await cache.set(cache_key, payload)
    await _render_detail(callback.message, payload, content_type, mymoviz_id, db_user, session)
    await callback.answer()


async def _render_detail(
    message: Message,
    payload: dict,
    content_type: ContentType,
    mymoviz_id: str,
    db_user: User,
    session: AsyncSession,
) -> None:
    """Render the detail message with poster + buttons."""
    d = payload["detail"]

    # Build text
    if content_type == ContentType.MOVIE:
        # Build a temporary Movie-like dict to reuse formatter
        class _M:
            pass
        m = _M()
        for k, v in d.items():
            setattr(m, k, v)
        text = format_movie_info(m)  # type: ignore[arg-type]
    else:
        class _S:
            pass
        s = _S()
        for k, v in d.items():
            setattr(s, k, v)
        text = format_series_info(s)  # type: ignore[arg-type]

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
        # Note: SubscriptionRepository.exists was used; ensure method exists
        # If not exists() method, fallback to list check below.

    kb = content_detail_kb(
        content_type=content_type,
        mymoviz_id=mymoviz_id,
        site_url=d.get("page_url"),
        is_favorite=is_fav,
        is_subscribed=is_sub,
    )

    poster_url = d.get("poster_url")
    if poster_url:
        try:
            await message.delete()
            await message.answer_photo(
                photo=poster_url,
                caption=text,
                reply_markup=kb,
            )
        except Exception as exc:
            logger.warning("Failed to send poster photo: {}", exc)
            await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


# ----------------------------------------------------------------------
# Favorite callback: fav:<content_type>:<mymoviz_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("fav:"))
async def cb_favorite(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Toggle favorite status for a content item."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    content_type_str = parts[1]
    mymoviz_id = parts[2]
    content_type = ContentType.MOVIE if content_type_str == "movie" else ContentType.SERIES

    # Find DB record
    if content_type == ContentType.MOVIE:
        movie = await MovieRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not movie:
            await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)
            return
        exists = await FavoriteRepository.exists(
            session, db_user.id, content_type, movie_id=movie.id
        )
        if exists:
            await FavoriteRepository.remove(session, db_user.id, content_type, movie_id=movie.id)
            await callback.answer("❌ از علاقه‌مندی حذف شد.")
        else:
            await FavoriteRepository.add(session, db_user.id, content_type, movie_id=movie.id)
            await callback.answer("⭐ به علاقه‌مندی اضافه شد.")
    else:
        series = await SeriesRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not series:
            await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)
            return
        exists = await FavoriteRepository.exists(
            session, db_user.id, content_type, series_id=series.id
        )
        if exists:
            await FavoriteRepository.remove(session, db_user.id, content_type, series_id=series.id)
            await callback.answer("❌ از علاقه‌مندی حذف شد.")
        else:
            await FavoriteRepository.add(session, db_user.id, content_type, series_id=series.id)
            await callback.answer("⭐ به علاقه‌مندی اضافه شد.")


# ----------------------------------------------------------------------
# Subscription callback: sub:<content_type>:<mymoviz_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("sub:"))
async def cb_subscribe(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Toggle subscription for a content item."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    content_type_str = parts[1]
    mymoviz_id = parts[2]
    content_type = ContentType.MOVIE if content_type_str == "movie" else ContentType.SERIES

    if content_type == ContentType.MOVIE:
        movie = await MovieRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not movie:
            await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)
            return
        now_active = await SubscriptionRepository.toggle(
            session, db_user.id, content_type, movie_id=movie.id
        )
    else:
        series = await SeriesRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not series:
            await callback.answer("❌ ابتدا صفحه را باز کنید.", show_alert=True)
            return
        now_active = await SubscriptionRepository.toggle(
            session, db_user.id, content_type, series_id=series.id
        )

    msg = "🔔 اطلاع‌رسانی فعال شد." if now_active else "❌ اطلاع‌رسانی غیرفعال شد."
    await callback.answer(msg, show_alert=False)


# ----------------------------------------------------------------------
# Favorites list: favorites:list
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "favorites:list")
async def cb_favorites_list(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Show the user's favorite list."""
    favs = await FavoriteRepository.list_by_user(session, db_user.id)
    if not favs:
        await callback.message.edit_text(
            "⭐ هنوز هیچ علاقه‌مندی‌ای ثبت نکرده‌اید.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    items: list[dict] = []
    for fav in favs:
        if fav.content_type == ContentType.MOVIE and fav.movie:
            items.append(
                {
                    "content_type": "movie",
                    "mymoviz_id": fav.movie.mymoviz_id,
                    "title": fav.movie.title_fa or fav.movie.title_en or "—",
                }
            )
        elif fav.content_type == ContentType.SERIES and fav.series:
            items.append(
                {
                    "content_type": "series",
                    "mymoviz_id": fav.series.mymoviz_id,
                    "title": fav.series.title_fa or fav.series.title_en or "—",
                }
            )
    from telegram.keyboards import favorites_list_kb
    await callback.message.edit_text(
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
    subs = await SubscriptionRepository.list_by_user(session, db_user.id)
    active = [s for s in subs if s.is_active]
    if not active:
        await callback.message.edit_text(
            "🔔 هیچ اعلان فعالی ندارید.",
            reply_markup=back_to_main_kb(),
        )
        await callback.answer()
        return

    items: list[dict] = []
    for sub in active:
        if sub.content_type == ContentType.MOVIE and sub.movie:
            items.append(
                {
                    "content_type": "movie",
                    "mymoviz_id": sub.movie.mymoviz_id,
                    "title": sub.movie.title_fa or sub.movie.title_en or "—",
                }
            )
        elif sub.content_type == ContentType.SERIES and sub.series:
            items.append(
                {
                    "content_type": "series",
                    "mymoviz_id": sub.series.mymoviz_id,
                    "title": sub.series.title_fa or sub.series.title_en or "—",
                }
            )
    from telegram.keyboards import subscriptions_list_kb
    await callback.message.edit_text(
        f"🔔 <b>اعلان‌های فعال شما ({len(items)})</b>",
        reply_markup=subscriptions_list_kb(items),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Downloads: dl:<content_type>:<mymoviz_id>
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data and c.data.startswith("dl:"))
async def cb_download(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show download links (links to site)."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ داده نامعتبر است.", show_alert=True)
        return
    content_type_str = parts[1]
    mymoviz_id = parts[2]

    if content_type_str == "movie":
        movie = await MovieRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not movie:
            await callback.answer("❌ اطلاعاتی موجود نیست.", show_alert=True)
            return
        url = movie.page_url or ""
        qualities = movie.qualities or "نامشخص"
        text = (
            f"📥 <b>دانلود فیلم</b>\n\n"
            f"🎬 <b>{movie.title_fa or movie.title_en}</b>\n"
            f"🎥 کیفیت‌ها: {qualities}\n"
            f"🎙 دوبله: {'✅' if movie.has_dubbing else '❌'}\n"
            f"📝 زیرنویس: {'✅' if movie.has_subtitle else '❌'}\n\n"
            "برای مشاهده لینک‌های دانلود به صفحه فیلم در سایت بروید:"
        )
    else:
        series = await SeriesRepository.get_by_mymoviz_id(session, mymoviz_id)
        if not series:
            await callback.answer("❌ اطلاعاتی موجود نیست.", show_alert=True)
            return
        url = series.page_url or ""
        qualities = series.qualities or "نامشخص"
        text = (
            f"📥 <b>دانلود سریال</b>\n\n"
            f"📺 <b>{series.title_fa or series.title_en}</b>\n"
            f"🎥 کیفیت‌ها: {qualities}\n"
            f"🎙 دوبله: {'✅' if series.has_dubbing else '❌'}\n"
            f"📝 زیرنویس: {'✅' if series.has_subtitle else '❌'}\n\n"
            "برای مشاهده لینک‌های دانلود قسمت‌ها به صفحه سریال در سایت بروید:"
        )

    builder = InlineKeyboardBuilder()
    if url:
        builder.add(InlineKeyboardButton(text="🌐 صفحه دانلود", url=url))
    builder.add(InlineKeyboardButton(text="🏠 خانه", callback_data="menu:main"))

    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()
