"""
SQLAlchemy ORM models for the MyMoviz Notify Bot database.

Schema overview
---------------
* User           - registered Telegram users
* Movie          - cached movie metadata from mymoviz.co
* Series         - cached series metadata
* Episode        - episodes belonging to a series
* Favorite       - user favorites (movies or series)
* Subscription   - notification subscriptions per user/content
* Notification   - log of notifications already dispatched (dedupe)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


class ContentType(str, Enum):
    """Discriminator for movie vs series content."""

    MOVIE = "movie"
    SERIES = "series"


class NotificationType(str, Enum):
    """Reason a notification is being sent."""

    NEW_EPISODE = "new_episode"
    NEW_QUALITY = "new_quality"
    NEW_DUBBING = "new_dubbing"
    NEW_SUBTITLE = "new_subtitle"
    NEW_CONTENT = "new_content"


class User(Base):
    """A Telegram user who has interacted with the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="fa")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class Movie(Base):
    """Cached movie metadata."""

    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mymoviz_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title_fa: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    genres: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qualities: Mapped[str | None] = mapped_column(String(512), nullable=True)
    has_dubbing: Mapped[bool] = mapped_column(Boolean, default=False)
    has_subtitle: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Movie(id={self.id}, title_fa={self.title_fa})>"


class Series(Base):
    """Cached series metadata."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mymoviz_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title_fa: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imdb_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    genres: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qualities: Mapped[str | None] = mapped_column(String(512), nullable=True)
    has_dubbing: Mapped[bool] = mapped_column(Boolean, default=False)
    has_subtitle: Mapped[bool] = mapped_column(Boolean, default=False)
    latest_episode: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Series(id={self.id}, title_fa={self.title_fa})>"


class Episode(Base):
    """An episode belonging to a series."""

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False, index=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    qualities: Mapped[str | None] = mapped_column(String(512), nullable=True)
    has_dubbing: Mapped[bool] = mapped_column(Boolean, default=False)
    has_subtitle: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    series: Mapped["Series"] = relationship(back_populates="episodes")

    __table_args__ = (UniqueConstraint("series_id", "season", "episode", name="uq_series_season_ep"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Episode(S{self.season}E{self.episode} series_id={self.series_id})>"


class Favorite(Base):
    """User favorite (movie or series)."""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content_type: Mapped[ContentType] = mapped_column(SQLEnum(ContentType), nullable=False)
    movie_id: Mapped[int | None] = mapped_column(ForeignKey("movies.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="favorites")
    movie: Mapped["Movie | None"] = relationship(back_populates="favorites")
    series: Mapped["Series | None"] = relationship(back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "content_type", "movie_id", "series_id", name="uq_favorite"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Favorite(user_id={self.user_id}, type={self.content_type})>"


class Subscription(Base):
    """A user-subscribed notification for a specific movie/series."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content_type: Mapped[ContentType] = mapped_column(SQLEnum(ContentType), nullable=False)
    movie_id: Mapped[int | None] = mapped_column(ForeignKey("movies.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    movie: Mapped["Movie | None"] = relationship(back_populates="subscriptions")
    series: Mapped["Series | None"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "content_type", "movie_id", "series_id", name="uq_subscription"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscription(user_id={self.user_id}, type={self.content_type})>"


class Notification(Base):
    """A log of dispatched notifications (used for deduplication and stats)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    content_type: Mapped[ContentType] = mapped_column(SQLEnum(ContentType), nullable=False)
    movie_id: Mapped[int | None] = mapped_column(ForeignKey("movies.id"), nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"), nullable=True)
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType), nullable=False
    )
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    movie: Mapped["Movie | None"] = relationship(back_populates="notifications")
    series: Mapped["Series | None"] = relationship(back_populates="notifications")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification(id={self.id}, type={self.notification_type})>"


class CallbackMapping(Base):
    """Short-key -> (content_type, mymoviz_id) mapping for Telegram callback_data.

    Telegram limits ``callback_data`` to 64 bytes. Some MyMoviz IDs are
    very long (e.g. ``tvshows/tt43357366/The-Apartment-Job-2026`` = 41 chars),
    so we hash them to 8 chars and store the mapping here. Entries are
    cleaned up periodically (default: every 10 minutes) by the scheduler.
    """

    __tablename__ = "callback_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_key: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mymoviz_id: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CallbackMapping(short={self.short_key}, type={self.content_type})>"
