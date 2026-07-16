"""
Unit tests for database models and repositories.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from database.database import db_manager, init_db
from database.models import (
    ContentType,
    Favorite,
    NotificationType,
    Subscription,
    User,
)
from database.repositories import (
    FavoriteRepository,
    MovieRepository,
    NotificationRepository,
    SeriesRepository,
    SubscriptionRepository,
    UserRepository,
)


@pytest_asyncio.fixture
async def db_session():
    """Initialize the database and yield a session for each test."""
    await init_db()
    async with db_manager.session() as session:
        yield session
    await db_manager.dispose()
    # Clean up test DB file
    import os
    if os.path.exists("./data/test.db"):
        os.remove("./data/test.db")


@pytest.mark.asyncio
async def test_user_repository_get_or_create(db_session) -> None:
    """User is created on first call and returned on subsequent calls."""
    user1 = await UserRepository.get_or_create(
        db_session, telegram_id=999, username="alice", first_name="Alice"
    )
    assert user1.id is not None
    assert user1.telegram_id == 999
    assert user1.username == "alice"

    user2 = await UserRepository.get_or_create(
        db_session, telegram_id=999, username="alice2"
    )
    assert user2.id == user1.id
    assert user2.username == "alice2"  # updated


@pytest.mark.asyncio
async def test_user_repository_count(db_session) -> None:
    await UserRepository.get_or_create(db_session, telegram_id=1)
    await UserRepository.get_or_create(db_session, telegram_id=2)
    count = await UserRepository.count_all(db_session)
    assert count >= 2


@pytest.mark.asyncio
async def test_movie_upsert(db_session) -> None:
    data = {
        "mymoviz_id": "test-movie-1",
        "title_fa": "فیلم تست",
        "title_en": "Test Movie",
        "year": 2024,
        "imdb_rating": 8.0,
    }
    movie = await MovieRepository.upsert(db_session, data)
    assert movie.id is not None
    assert movie.title_fa == "فیلم تست"

    # Upsert again with updated rating
    data2 = dict(data)
    data2["imdb_rating"] = 9.5
    movie2 = await MovieRepository.upsert(db_session, data2)
    assert movie2.id == movie.id
    assert movie2.imdb_rating == 9.5


@pytest.mark.asyncio
async def test_subscription_toggle(db_session) -> None:
    user = await UserRepository.get_or_create(db_session, telegram_id=42)
    movie = await MovieRepository.upsert(
        db_session,
        {"mymoviz_id": "m1", "title_fa": "Movie 1"},
    )
    active1 = await SubscriptionRepository.toggle(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert active1 is True

    exists = await SubscriptionRepository.exists(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert exists is True

    active2 = await SubscriptionRepository.toggle(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert active2 is False


@pytest.mark.asyncio
async def test_favorite_add_remove(db_session) -> None:
    user = await UserRepository.get_or_create(db_session, telegram_id=100)
    movie = await MovieRepository.upsert(
        db_session, {"mymoviz_id": "f1", "title_fa": "Fav Movie"}
    )

    exists_before = await FavoriteRepository.exists(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert exists_before is False

    await FavoriteRepository.add(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )

    exists_after = await FavoriteRepository.exists(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert exists_after is True

    removed = await FavoriteRepository.remove(
        db_session, user.id, ContentType.MOVIE, movie_id=movie.id
    )
    assert removed is True


@pytest.mark.asyncio
async def test_notification_dedupe(db_session) -> None:
    """Already-sent notifications should be detected."""
    movie = await MovieRepository.upsert(
        db_session, {"mymoviz_id": "n1", "title_fa": "Notif Movie"}
    )
    sent_before = await NotificationRepository.already_sent(
        db_session,
        content_type=ContentType.MOVIE,
        notification_type=NotificationType.NEW_QUALITY,
        movie_id=movie.id,
        payload_hash="abc123",
    )
    assert sent_before is False

    await NotificationRepository.create(
        db_session,
        content_type=ContentType.MOVIE,
        notification_type=NotificationType.NEW_QUALITY,
        movie_id=movie.id,
        payload="abc123",
        channel="@test",
    )

    sent_after = await NotificationRepository.already_sent(
        db_session,
        content_type=ContentType.MOVIE,
        notification_type=NotificationType.NEW_QUALITY,
        movie_id=movie.id,
        payload_hash="abc123",
    )
    assert sent_after is True
