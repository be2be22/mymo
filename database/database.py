"""
Async SQLAlchemy database engine and session management.

Provides:
* ``db_manager`` - lazily-initialized async engine + session factory
* ``init_db``    - create tables (used at startup)
* ``get_session``- async context manager yielding sessions
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings, ensure_data_dir
from database.models import Base
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Encapsulates the async engine and session factory."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Return the initialized engine, raising if not initialized."""
        if self._engine is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory, raising if not initialized."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager not initialized. Call init() first.")
        return self._session_factory

    async def init(self) -> None:
        """Initialize the async engine and create all tables."""
        ensure_data_dir()
        logger.info("Initializing database: {}", settings.database_url)

        connect_args: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self._engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized and tables created/verified.")

    async def dispose(self) -> None:
        """Dispose of the engine. Safe to call multiple times."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database engine disposed.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async session, committing on success and rolling back on error."""
        if self._session_factory is None:
            raise RuntimeError("DatabaseManager not initialized.")
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# Module-level singleton used throughout the application
db_manager = DatabaseManager()


async def init_db() -> None:
    """Initialize the database (idempotent)."""
    await db_manager.init()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Convenience context manager mirroring ``db_manager.session()``."""
    async with db_manager.session() as session:
        yield session
