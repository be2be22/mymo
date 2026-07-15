"""
Repository layer - data-access helpers built on top of async SQLAlchemy.

Each repository exposes high-level operations used by the rest of the
application (handlers, scheduler, scrapers) so that SQL details stay
isolated here.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    ContentType,
    Episode,
    Favorite,
    Movie,
    Notification,
    NotificationType,
    Series,
    Subscription,
    User,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------
class UserRepository:
    """CRUD operations for :class:`User`."""

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name)
            session.add(user)
            await session.flush()
            logger.info("New user registered: telegram_id={}, username={}", telegram_id, username)
        else:
            if username != user.username or first_name != user.first_name:
                user.username = username
                user.first_name = first_name
                await session.flush()
        return user

    @staticmethod
    async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_all(session: AsyncSession) -> int:
        result = await session.execute(select(func.count(User.id)))
        return int(result.scalar_one())

    @staticmethod
    async def list_active_ids(session: AsyncSession) -> List[int]:
        stmt = select(User.telegram_id).where(User.is_active.is_(True), User.is_blocked.is_(False))
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


# ----------------------------------------------------------------------
# Movies
# ----------------------------------------------------------------------
class MovieRepository:
    """CRUD operations for :class:`Movie`."""

    @staticmethod
    async def upsert(session: AsyncSession, data: dict) -> Movie:
        mymoviz_id = data["mymoviz_id"]
        stmt = select(Movie).where(Movie.mymoviz_id == mymoviz_id)
        result = await session.execute(stmt)
        movie = result.scalar_one_or_none()
        if movie is None:
            movie = Movie(**data)
            session.add(movie)
            await session.flush()
            logger.debug("Inserted new movie: {}", data.get("title_fa") or data.get("title_en"))
        else:
            for key, value in data.items():
                setattr(movie, key, value)
            await session.flush()
        return movie

    @staticmethod
    async def get_by_mymoviz_id(session: AsyncSession, mymoviz_id: str) -> Optional[Movie]:
        stmt = select(Movie).where(Movie.mymoviz_id == mymoviz_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, movie_id: int) -> Optional[Movie]:
        return await session.get(Movie, movie_id)

    @staticmethod
    async def count_all(session: AsyncSession) -> int:
        result = await session.execute(select(func.count(Movie.id)))
        return int(result.scalar_one())

    @staticmethod
    async def list_all_for_check(session: AsyncSession) -> Sequence[Movie]:
        """Return all movies with active subscriptions for the scheduler."""
        stmt = (
            select(Movie)
            .join(Subscription, Subscription.movie_id == Movie.id)
            .where(Subscription.is_active.is_(True))
            .distinct()
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ----------------------------------------------------------------------
# Series
# ----------------------------------------------------------------------
class SeriesRepository:
    """CRUD operations for :class:`Series`."""

    @staticmethod
    async def upsert(session: AsyncSession, data: dict) -> Series:
        mymoviz_id = data["mymoviz_id"]
        stmt = select(Series).where(Series.mymoviz_id == mymoviz_id)
        result = await session.execute(stmt)
        series = result.scalar_one_or_none()
        if series is None:
            series = Series(**data)
            session.add(series)
            await session.flush()
            logger.debug("Inserted new series: {}", data.get("title_fa") or data.get("title_en"))
        else:
            for key, value in data.items():
                setattr(series, key, value)
            await session.flush()
        return series

    @staticmethod
    async def get_by_mymoviz_id(session: AsyncSession, mymoviz_id: str) -> Optional[Series]:
        stmt = select(Series).where(Series.mymoviz_id == mymoviz_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, series_id: int) -> Optional[Series]:
        return await session.get(Series, series_id)

    @staticmethod
    async def count_all(session: AsyncSession) -> int:
        result = await session.execute(select(func.count(Series.id)))
        return int(result.scalar_one())

    @staticmethod
    async def list_all_for_check(session: AsyncSession) -> Sequence[Series]:
        """Return all series with active subscriptions for the scheduler."""
        stmt = (
            select(Series)
            .join(Subscription, Subscription.series_id == Series.id)
            .where(Subscription.is_active.is_(True))
            .distinct()
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ----------------------------------------------------------------------
# Episodes
# ----------------------------------------------------------------------
class EpisodeRepository:
    """CRUD operations for :class:`Episode`."""

    @staticmethod
    async def upsert(session: AsyncSession, data: dict) -> Episode:
        series_id = data["series_id"]
        season = data.get("season")
        episode = data.get("episode")

        stmt = select(Episode).where(
            Episode.series_id == series_id,
            (Episode.season == season) if season is not None else Episode.season.is_(None),
            (Episode.episode == episode) if episode is not None else Episode.episode.is_(None),
        )
        result = await session.execute(stmt)
        ep = result.scalar_one_or_none()

        if ep is None:
            ep = Episode(**data)
            session.add(ep)
            await session.flush()
            logger.debug(
                "Inserted new episode: series_id={} S{}E{}",
                series_id, season, episode,
            )
        else:
            for key, value in data.items():
                setattr(ep, key, value)
            await session.flush()
        return ep

    @staticmethod
    async def list_by_series(session: AsyncSession, series_id: int) -> Sequence[Episode]:
        stmt = (
            select(Episode)
            .where(Episode.series_id == series_id)
            .order_by(Episode.season.desc().nulls_last(), Episode.episode.desc().nulls_last())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_latest(session: AsyncSession, series_id: int) -> Optional[Episode]:
        rows = await EpisodeRepository.list_by_series(session, series_id)
        return rows[0] if rows else None


# ----------------------------------------------------------------------
# Favorites
# ----------------------------------------------------------------------
class FavoriteRepository:
    """CRUD operations for :class:`Favorite`."""

    @staticmethod
    async def add(
        session: AsyncSession,
        user_id: int,
        content_type: ContentType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
    ) -> Favorite:
        fav = Favorite(
            user_id=user_id,
            content_type=content_type,
            movie_id=movie_id,
            series_id=series_id,
        )
        session.add(fav)
        try:
            await session.flush()
        except Exception:
            await session.rollback()
            raise
        return fav

    @staticmethod
    async def remove(
        session: AsyncSession,
        user_id: int,
        content_type: ContentType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
    ) -> bool:
        conditions = [
            Favorite.user_id == user_id,
            Favorite.content_type == content_type,
        ]
        if movie_id is not None:
            conditions.append(Favorite.movie_id == movie_id)
        if series_id is not None:
            conditions.append(Favorite.series_id == series_id)
        stmt = delete(Favorite).where(and_(*conditions))
        result = await session.execute(stmt)
        return (result.rowcount or 0) > 0

    @staticmethod
    async def exists(
        session: AsyncSession,
        user_id: int,
        content_type: ContentType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
    ) -> bool:
        conditions = [
            Favorite.user_id == user_id,
            Favorite.content_type == content_type,
        ]
        if movie_id is not None:
            conditions.append(Favorite.movie_id == movie_id)
        if series_id is not None:
            conditions.append(Favorite.series_id == series_id)
        stmt = select(func.count(Favorite.id)).where(and_(*conditions))
        result = await session.execute(stmt)
        return int(result.scalar_one()) > 0

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: int) -> Sequence[Favorite]:
        stmt = select(Favorite).where(Favorite.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().all()


# ----------------------------------------------------------------------
# Subscriptions
# ----------------------------------------------------------------------
class SubscriptionRepository:
    """CRUD operations for :class:`Subscription`."""

    @staticmethod
    async def toggle(
        session: AsyncSession,
        user_id: int,
        content_type: ContentType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
    ) -> bool:
        """Toggle a subscription. Returns True if now active, False otherwise."""
        conditions = [
            Subscription.user_id == user_id,
            Subscription.content_type == content_type,
        ]
        if movie_id is not None:
            conditions.append(Subscription.movie_id == movie_id)
        if series_id is not None:
            conditions.append(Subscription.series_id == series_id)
        stmt = select(Subscription).where(and_(*conditions))
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                content_type=content_type,
                movie_id=movie_id,
                series_id=series_id,
                is_active=True,
            )
            session.add(sub)
            await session.flush()
            return True
        sub.is_active = not sub.is_active
        await session.flush()
        return sub.is_active

    @staticmethod
    async def exists(
        session: AsyncSession,
        user_id: int,
        content_type: ContentType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
    ) -> bool:
        """Return True if an active subscription exists for this user/content."""
        conditions = [
            Subscription.user_id == user_id,
            Subscription.content_type == content_type,
            Subscription.is_active.is_(True),
        ]
        if movie_id is not None:
            conditions.append(Subscription.movie_id == movie_id)
        if series_id is not None:
            conditions.append(Subscription.series_id == series_id)
        stmt = select(func.count(Subscription.id)).where(and_(*conditions))
        result = await session.execute(stmt)
        return int(result.scalar_one()) > 0

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: int) -> Sequence[Subscription]:
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_all(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(Subscription.id)).where(Subscription.is_active.is_(True))
        )
        return int(result.scalar_one())


# ----------------------------------------------------------------------
# Notifications
# ----------------------------------------------------------------------
class NotificationRepository:
    """CRUD operations for :class:`Notification` (used for dedupe + stats)."""

    @staticmethod
    async def already_sent(
        session: AsyncSession,
        content_type: ContentType,
        notification_type: NotificationType,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
        episode_id: Optional[int] = None,
        payload_hash: Optional[str] = None,
    ) -> bool:
        conditions = [
            Notification.content_type == content_type,
            Notification.notification_type == notification_type,
        ]
        if movie_id is not None:
            conditions.append(Notification.movie_id == movie_id)
        if series_id is not None:
            conditions.append(Notification.series_id == series_id)
        if episode_id is not None:
            conditions.append(Notification.episode_id == episode_id)
        if payload_hash:
            conditions.append(Notification.payload == payload_hash)
        stmt = select(func.count(Notification.id)).where(and_(*conditions))
        result = await session.execute(stmt)
        return int(result.scalar_one()) > 0

    @staticmethod
    async def create(
        session: AsyncSession,
        content_type: ContentType,
        notification_type: NotificationType,
        user_id: Optional[int] = None,
        movie_id: Optional[int] = None,
        series_id: Optional[int] = None,
        episode_id: Optional[int] = None,
        payload: Optional[str] = None,
        channel: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            content_type=content_type,
            notification_type=notification_type,
            movie_id=movie_id,
            series_id=series_id,
            episode_id=episode_id,
            payload=payload,
            channel=channel,
            success=success,
            error_message=error_message,
        )
        session.add(notif)
        await session.flush()
        return notif

    @staticmethod
    async def count_all(session: AsyncSession) -> int:
        result = await session.execute(select(func.count(Notification.id)))
        return int(result.scalar_one())

    @staticmethod
    async def count_failed(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(Notification.id)).where(Notification.success.is_(False))
        )
        return int(result.scalar_one())


__all__ = [
    "EpisodeRepository",
    "FavoriteRepository",
    "MovieRepository",
    "NotificationRepository",
    "SeriesRepository",
    "SubscriptionRepository",
    "UserRepository",
]
