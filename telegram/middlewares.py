"""
Aiogram middlewares - inject DB session & user info into each update.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User as TgUser

from database.database import db_manager
from database.models import User
from database.repositories import UserRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Open a DB session per update and attach it to ``data["session"]``.

    Also ensures the user is registered/updated in the database, attaching
    the ORM :class:`User` instance to ``data["db_user"]``.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        async with db_manager.session() as session:
            data["session"] = session
            db_user: User | None = None
            if tg_user is not None:
                try:
                    db_user = await UserRepository.get_or_create(
                        session,
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                        first_name=tg_user.first_name,
                    )
                except Exception as exc:
                    logger.warning("DatabaseMiddleware user upsert failed: {}", exc)
            data["db_user"] = db_user
            try:
                return await handler(event, data)
            finally:
                data.pop("session", None)
                data.pop("db_user", None)
