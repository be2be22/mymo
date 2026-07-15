"""Custom filters for aiogram handlers."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from config.settings import settings


class IsAdminFilter(BaseFilter):
    """Pass only if the message sender is a configured admin."""

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return message.from_user.id in settings.admin_id_list


# Singleton instance used in handlers
is_admin_filter = IsAdminFilter()
