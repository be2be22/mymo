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
    CallbackMappingRepository,
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
    """Initialize the APScheduler and register the check job.

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
    logger.info(
        "Scheduler configured: every {} minute(s).", settings.check_interval_minutes
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

        # Cleanup expired callback mappings (older than 10 minutes)
        try:
            async with db_manager.session() as session:
                deleted = await CallbackMappingRepository.cleanup_expired(
                    session, max_age_minutes=10
                )
                if deleted > 0:
                    logger.info("Cleaned up {} expired callback mappings", deleted)
        except Exception as exc:
            logger.debug("Callback mapping cleanup failed: {}", exc)

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

    # Send to channels
    from main import bot  # late import to avoid circular

    channel_ids = settings.channel_id_list
    for channel in channel_ids:
        try:
            await bot.send_message(
                chat_id=channel,
                text=message_text,
                disable_web_page_preview=True,
            )
            async with db_manager.session() as session:
                await NotificationRepository.create(
                    session,
                    content_type=content_type,
                    notification_type=notification_type,
                    movie_id=movie_id,
                    series_id=series_id,
                    payload=payload_hash,
                    channel=channel,
                    success=True,
                )
            logger.info("Notification sent to channel {} for '{}'", channel, title)
        except Exception as exc:
            logger.warning("Failed to send to channel {}: {}", channel, exc)
            async with db_manager.session() as session:
                await NotificationRepository.create(
                    session,
                    content_type=content_type,
                    notification_type=notification_type,
                    movie_id=movie_id,
                    series_id=series_id,
                    payload=payload_hash,
                    channel=channel,
                    success=False,
                    error_message=str(exc),
                )

    # Send to subscribed users
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
