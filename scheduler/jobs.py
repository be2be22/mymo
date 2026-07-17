"""
APScheduler jobs - periodic check for new episodes / qualities / dubbing /
subtitles on subscribed movies and series.

Runs every 10 minutes (configurable via ``CHECK_INTERVAL_MINUTES``).
For each subscribed content:
  1. Re-scrape the detail page
  2. Compare new data with stored data (raw_hash + structured fields)
  3. Dispatch notifications to subscribed users + configured channels
  4. Update stored data
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from database.database import db_manager
from database.models import ContentType, NotificationType
from database.repositories import (
    EpisodeRepository,
    MovieRepository,
    NotificationRepository,
    SeriesRepository,
    SubscriptionRepository,
    UserRepository,
)
from scrapers.manager import scraper_manager
from utils.formatters import format_notification_message
from utils.helpers import hash_payload
from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level scheduler singleton
_scheduler: Optional[AsyncIOScheduler] = None


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------
def setup_scheduler() -> AsyncIOScheduler:
    """Initialize the APScheduler and register jobs.

    Jobs:
    1. check_subscriptions - every 10 min, checks subscribed content for changes
    2. check_new_content - every 60 min, posts new movies/series to channel

    The returned scheduler is NOT started here; the caller (main.py)
    starts it inside the running event loop.
    """
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_check_now,
        trigger=IntervalTrigger(minutes=settings.check_interval_minutes),
        id="check_subscriptions",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        run_new_content_check,
        trigger=IntervalTrigger(minutes=settings.new_content_check_interval_minutes),
        id="check_new_content",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Scheduler configured: subscriptions every {} min, new content every {} min",
        settings.check_interval_minutes,
        settings.new_content_check_interval_minutes,
    )
    return _scheduler


async def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler shut down.")


# ----------------------------------------------------------------------
# Main job
# ----------------------------------------------------------------------
async def run_check_now() -> None:
    """Run a single check pass for all subscriptions.

    This is the function invoked by APScheduler. It can also be triggered
    manually by an admin via the admin panel.
    """
    logger.info("⏰ Scheduler tick: checking subscriptions...")
    try:
        async with db_manager.session() as session:
            movies = await MovieRepository.list_all_for_check(session)
            series_list = await SeriesRepository.list_all_for_check(session)

        logger.info("Subscribed content to check: {} movies, {} series",
                    len(movies), len(series_list))

        # Run checks concurrently (bounded)
        tasks: List[asyncio.Task] = []
        for movie in movies:
            tasks.append(asyncio.create_task(_check_movie(movie.id)))
        for series in series_list:
            tasks.append(asyncio.create_task(_check_series(series.id)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Cache cleanup
        from cache.cache_manager import cache
        await cache.cleanup_expired()

        logger.info("✅ Scheduler tick complete.")
    except Exception as exc:
        logger.exception("Scheduler tick failed: {}", exc)


# ----------------------------------------------------------------------
# Movie check
# ----------------------------------------------------------------------
async def _check_movie(movie_id: int) -> None:
    """Re-scrape a movie and dispatch notifications for any change."""
    try:
        async with db_manager.session() as session:
            movie = await MovieRepository.get_by_id(session, movie_id)
            if not movie:
                return
            mymoviz_id = movie.mymoviz_id
            old_hash = movie.raw_hash
            old_qualities = movie.qualities or ""
            old_dubbing = movie.has_dubbing
            old_subtitle = movie.has_subtitle
            title = movie.title_fa or movie.title_en or "فیلم"

        detail = await scraper_manager.get_content_detail(mymoviz_id, "movie")
        if not detail:
            logger.debug("Movie {} detail unavailable; skipping.", mymoviz_id)
            return

        changes: List[tuple[NotificationType, str]] = []

        # Hash-level change detection (any change)
        if old_hash and detail.raw_hash and old_hash != detail.raw_hash:
            logger.info("Movie {} hash changed: {} -> {}", mymoviz_id, old_hash, detail.raw_hash)

        # Quality change detection
        new_qualities = detail.qualities or ""
        if new_qualities and new_qualities != old_qualities:
            # Find newly added qualities
            old_set = {q.strip() for q in old_qualities.split(",") if q.strip()}
            new_set = {q.strip() for q in new_qualities.split(",") if q.strip()}
            added = new_set - old_set
            if added:
                changes.append((NotificationType.NEW_QUALITY, f"🎥 کیفیت جدید: {', '.join(added)}"))

        # Dubbing change
        if detail.has_dubbing and not old_dubbing:
            changes.append((NotificationType.NEW_DUBBING, "🎙 دوبله جدید اضافه شد"))

        # Subtitle change
        if detail.has_subtitle and not old_subtitle:
            changes.append((NotificationType.NEW_SUBTITLE, "📝 زیرنویس جدید اضافه شد"))

        if not changes:
            return

        # Update stored movie
        async with db_manager.session() as session:
            await MovieRepository.upsert(
                session,
                {
                    "mymoviz_id": mymoviz_id,
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
                    "raw_hash": detail.raw_hash,
                },
            )

        # Dispatch notifications
        for notif_type, extra in changes:
            await _dispatch_notifications(
                content_type=ContentType.MOVIE,
                notification_type=notif_type,
                movie_id=movie_id,
                title=title,
                extra=extra,
                site_url=detail.page_url or "",
                payload_hash=hash_payload(f"movie:{movie_id}:{notif_type.value}:{extra}"),
            )
    except Exception as exc:
        logger.exception("Movie check failed for id={}: {}", movie_id, exc)


# ----------------------------------------------------------------------
# Series check
# ----------------------------------------------------------------------
async def _check_series(series_id: int) -> None:
    """Re-scrape a series and dispatch notifications for new episodes."""
    try:
        async with db_manager.session() as session:
            series = await SeriesRepository.get_by_id(session, series_id)
            if not series:
                return
            mymoviz_id = series.mymoviz_id
            old_hash = series.raw_hash
            old_qualities = series.qualities or ""
            old_dubbing = series.has_dubbing
            old_subtitle = series.has_subtitle
            old_latest_ep = series.latest_episode
            title = series.title_fa or series.title_en or "سریال"

        detail = await scraper_manager.get_content_detail(mymoviz_id, "series")
        if not detail:
            logger.debug("Series {} detail unavailable; skipping.", mymoviz_id)
            return

        changes: List[tuple[NotificationType, str]] = []
        new_episodes: List = []

        # Quality / dubbing / subtitle changes (same logic as movies)
        new_qualities = detail.qualities or ""
        if new_qualities and new_qualities != old_qualities:
            old_set = {q.strip() for q in old_qualities.split(",") if q.strip()}
            new_set = {q.strip() for q in new_qualities.split(",") if q.strip()}
            added = new_set - old_set
            if added:
                changes.append((NotificationType.NEW_QUALITY, f"🎥 کیفیت جدید: {', '.join(added)}"))

        if detail.has_dubbing and not old_dubbing:
            changes.append((NotificationType.NEW_DUBBING, "🎙 دوبله جدید اضافه شد"))
        if detail.has_subtitle and not old_subtitle:
            changes.append((NotificationType.NEW_SUBTITLE, "📝 زیرنویس جدید اضافه شد"))

        # New episode detection
        if detail.episodes:
            # Get currently-stored episodes
            async with db_manager.session() as session:
                existing_eps = await EpisodeRepository.list_by_series(session, series_id)
            existing_keys = {
                (e.season, e.episode) for e in existing_eps
            }
            for ep in detail.episodes:
                key = (ep.season, ep.episode)
                if key not in existing_keys:
                    new_episodes.append(ep)
            if new_episodes:
                # Sort new episodes oldest first for natural ordering
                new_episodes.sort(
                    key=lambda e: (e.season or 0, e.episode or 0)
                )
                for ep in new_episodes:
                    label = f"فصل {ep.season or '?'} قسمت {ep.episode or '?'}"
                    changes.append((NotificationType.NEW_EPISODE, f"🆕 قسمت جدید: {label}"))

        if not changes:
            return

        # Update stored series + persist new episodes
        async with db_manager.session() as session:
            await SeriesRepository.upsert(
                session,
                {
                    "mymoviz_id": mymoviz_id,
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
                },
            )
            for ep in new_episodes:
                await EpisodeRepository.upsert(
                    session,
                    {
                        "series_id": series_id,
                        "season": ep.season,
                        "episode": ep.episode,
                        "title": ep.title,
                        "page_url": ep.page_url,
                        "qualities": ep.qualities,
                        "has_dubbing": ep.has_dubbing,
                        "has_subtitle": ep.has_subtitle,
                    },
                )

        # Dispatch
        for notif_type, extra in changes:
            await _dispatch_notifications(
                content_type=ContentType.SERIES,
                notification_type=notif_type,
                series_id=series_id,
                title=title,
                extra=extra,
                site_url=detail.page_url or "",
                payload_hash=hash_payload(f"series:{series_id}:{notif_type.value}:{extra}"),
            )
    except Exception as exc:
        logger.exception("Series check failed for id={}: {}", series_id, exc)


# ----------------------------------------------------------------------
# Dispatch helpers
# ----------------------------------------------------------------------
async def _dispatch_notifications(
    content_type: ContentType,
    notification_type: NotificationType,
    title: str,
    extra: str,
    site_url: str,
    payload_hash: str,
    movie_id: Optional[int] = None,
    series_id: Optional[int] = None,
) -> None:
    """Send a notification to subscribed users + configured channels.

    De-duplicates per (content, type, payload) so the same change is not
    notified twice across scheduler ticks.
    """
    # Dedupe via DB
    async with db_manager.session() as session:
        if await NotificationRepository.already_sent(
            session,
            content_type=content_type,
            notification_type=notification_type,
            movie_id=movie_id,
            series_id=series_id,
            payload_hash=payload_hash,
        ):
            logger.debug("Notification already sent; skipping. payload={}", payload_hash)
            return

    message_text = format_notification_message(
        content_type=content_type,
        notification_type=notification_type,
        title=title,
        extra=extra,
        site_url=site_url or None,
    )

    # Notifications go ONLY to subscribed users (not to channel).
    # The channel is used exclusively for posting NEW content (movies/series)
    # via run_new_content_check, not for per-content change notifications.
    from telegram.bot_instance import get_bot; bot = get_bot()  # late import to avoid circular

    try:
        async with db_manager.session() as session:
            subs = await SubscriptionRepository.list_by_user(
                session, 0  # placeholder; we'll fetch all subscribers below
            )
            # The above won't work; fetch per-content subscribers
            from sqlalchemy import select
            from database.models import Subscription, User
            conditions = [
                Subscription.content_type == content_type,
                Subscription.is_active.is_(True),
            ]
            if movie_id is not None:
                conditions.append(Subscription.movie_id == movie_id)
            if series_id is not None:
                conditions.append(Subscription.series_id == series_id)
            stmt = (
                select(Subscription.user_id, User.telegram_id)
                .join(User, User.id == Subscription.user_id)
                .where(*conditions)
            )
            result = await session.execute(stmt)
            subscriber_telegram_ids = [row[1] for row in result.all()]
    except Exception as exc:
        logger.exception("Failed to fetch subscribers: {}", exc)
        subscriber_telegram_ids = []

    sent_count = 0
    failed_count = 0
    for tg_id in subscriber_telegram_ids:
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=message_text,
                disable_web_page_preview=True,
            )
            sent_count += 1
            await asyncio.sleep(0.04)  # rate limit ~25/sec
        except Exception as exc:
            failed_count += 1
            logger.debug("DM to {} failed: {}", tg_id, exc)

    logger.info(
        "Dispatched {} notifications to users (sent={}, failed={}).",
        notification_type.value, sent_count, failed_count,
    )

    # Record aggregate notification log entry for users
    async with db_manager.session() as session:
        await NotificationRepository.create(
            session,
            content_type=content_type,
            notification_type=notification_type,
            movie_id=movie_id,
            series_id=series_id,
            payload=payload_hash,
            channel="users",
            success=True,
        )


# ----------------------------------------------------------------------
# New content check job - posts new movies/series to channel every hour
# ----------------------------------------------------------------------
async def run_new_content_check() -> None:
    """Check for new movies/series and post them to the configured channel.

    Uses the modern home page's "آخرین بروزرسانی فیلم ها" and
    "سریال‌های به‌روز شده" sections to find new content.

    Tracks the last posted content IDs in the cache to avoid reposting.
    Only posts content that wasn't posted before.
    """
    logger.info("🆕 New content check: scanning modern home page...")
    try:
        from cache.cache_manager import cache
        from scrapers.manager import scraper_manager
        from telegram.bot_instance import get_bot; bot = get_bot()
        from config.settings import settings as cfg
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        # Fetch latest updates (10 movies + 10 series)
        latest_movies, latest_series = await scraper_manager.get_latest_updates(limit=10)
        logger.info(
            "Found {} latest movies and {} latest series",
            len(latest_movies), len(latest_series),
        )

        # Get previously posted IDs from cache
        posted_key = "posted_content_ids"
        posted = await cache.get(posted_key)
        if posted is None:
            posted = set()
        else:
            posted = set(posted)

        # Get bot username for deep links
        try:
            bot_me = await bot.get_me()
            bot_username = bot_me.username
        except Exception:
            bot_username = None

        channel_ids = cfg.channel_id_list
        if not channel_ids:
            logger.warning("No channel IDs configured - skipping new content post")
            return

        new_items: list = []
        # Combine movies and series, preserving order
        for item in latest_movies + latest_series:
            item_id = item.mymoviz_id
            if not item_id:
                continue
            if item_id in posted:
                continue
            new_items.append(item)

        if not new_items:
            logger.info("No new content to post (all already posted)")
            return

        logger.info("Posting {} new items to channel(s)", len(new_items))

        for item in new_items:
            try:
                await _post_content_to_channel(item, channel_ids, bot_username)
                posted.add(item.mymoviz_id)
                # Cache for 7 days (10080 minutes)
                await cache.set(posted_key, list(posted), ttl=604800)
                # Rate limit between posts
                await asyncio.sleep(2)
            except Exception as exc:
                logger.warning("Failed to post item {} to channel: {}", item.mymoviz_id, exc)

        logger.info("✅ New content check complete. Posted {} items.", len(new_items))
    except Exception as exc:
        logger.exception("New content check failed: {}", exc)


async def _post_content_to_channel(item, channel_ids: list, bot_username: Optional[str]) -> None:
    """Post a single content item to all configured channels.

    Sends a photo with poster + info caption + 2 inline buttons:
    - 🌐 مشاهده در سایت → opens the MyMoviz page
    - 🎬 مشاهده در ربات → opens the bot with a deep link to the content
    """
    from telegram.bot_instance import get_bot; bot = get_bot()
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    # Determine content type label
    content_type_str = item.content_type or "movie"
    icon = "🎬" if content_type_str == "movie" else "📺"
    type_label = "فیلم" if content_type_str == "movie" else "سریال"

    # Build caption
    title_fa = item.title_fa or "—"
    title_en = item.title_en or ""
    year = item.year or ""
    rating = item.imdb_rating
    summary = getattr(item, "_summary", None) or ""
    genres = getattr(item, "_genres", None) or ""
    latest_ep = getattr(item, "_latest_episode", None) or ""

    lines = [f"{icon} <b>{title_fa}</b>"]
    if title_en:
        lines.append(f"<i>{title_en}</i>")
    lines.append("")
    if year:
        lines.append(f"📅 سال: {year}")
    if rating:
        lines.append(f"⭐ IMDb: {rating}")
    if genres:
        lines.append(f"🎭 ژانر: {genres}")
    if latest_ep:
        lines.append(f"🆕 آخرین قسمت: {latest_ep}")
    lines.append(f"📦 نوع: {type_label}")
    if summary:
        # Truncate summary to keep caption under Telegram's 1024 char limit
        summary = summary[:500]
        lines.append("")
        lines.append(f"📖 {summary}")

    caption = "\n".join(lines)

    # Build inline keyboard with 2 buttons
    builder = InlineKeyboardBuilder()
    if item.page_url:
        builder.button(text="🌐 مشاهده در سایت", url=item.page_url)
    if bot_username and item.mymoviz_id:
        # Deep link to bot: https://t.me/<bot_username>?start=<content_id>
        # The bot's /start handler will process this and show the detail page
        deep_link = f"https://t.me/{bot_username}?start={item.mymoviz_id}"
        builder.button(text="🎬 مشاهده در ربات", url=deep_link)
    builder.adjust(1)

    # Send to each channel
    for channel_id in channel_ids:
        try:
            if item.poster_url:
                await bot.send_photo(
                    chat_id=channel_id,
                    photo=item.poster_url,
                    caption=caption,
                    reply_markup=builder.as_markup(),
                )
            else:
                await bot.send_message(
                    chat_id=channel_id,
                    text=caption,
                    reply_markup=builder.as_markup(),
                    disable_web_page_preview=True,
                )
            logger.info("Posted {} to channel {}", item.title_fa or item.title_en, channel_id)
        except Exception as exc:
            logger.warning("Failed to post to channel {}: {}", channel_id, exc)
