"""
Dispatcher setup - register all routers and middlewares.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings
from telegram.handlers.admin import router as admin_router
from telegram.handlers.listings import router as listings_router
from telegram.handlers.movie import router as movie_router
from telegram.handlers.search import router as search_router
from telegram.handlers.user import router as user_router
from telegram.middlewares import DatabaseMiddleware
from utils.logger import get_logger

logger = get_logger(__name__)


def setup_dispatcher(bot: Bot | None = None) -> Dispatcher:
    """Build and configure the aiogram Dispatcher.

    The ``bot`` argument is optional here; it is only used so the
    middleware's outer scope can see the bot if needed.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # Register middleware on Update level so every handler gets a DB session.
    dp.update.outer_middleware(DatabaseMiddleware())

    # Register routers (order matters: more specific first)
    dp.include_router(user_router)
    dp.include_router(search_router)
    dp.include_router(listings_router)
    dp.include_router(movie_router)
    dp.include_router(admin_router)

    logger.info(
        "Dispatcher configured with {} routers.",
        len([user_router, search_router, listings_router, movie_router, admin_router]),
    )
    return dp
