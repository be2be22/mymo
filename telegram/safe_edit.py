"""
Helper functions for safely editing Telegram messages.

Telegram has separate methods for editing text messages vs photo messages
(with captions). Calling ``edit_text`` on a photo message raises
``TelegramBadRequest: there is no text in the message to edit``.

This module provides a unified ``safe_edit_message`` that picks the right
method based on the message type, and falls back gracefully.
"""

from __future__ import annotations

from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardMarkup,
    Message,
)
from utils.logger import get_logger

logger = get_logger(__name__)


async def safe_edit_message(
    message: Message,
    text: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    disable_web_page_preview: bool = True,
) -> bool:
    """Edit a message safely, whether it's a text or photo message.

    - If the message has a photo: uses ``edit_caption`` (text becomes the caption).
    - If the message has text: uses ``edit_text``.
    - If editing fails (e.g. content is identical), the error is logged
      but not raised.

    Returns True if the edit succeeded, False otherwise.
    """
    try:
        if message.photo:
            await message.edit_caption(
                caption=text or "",
                reply_markup=reply_markup,
            )
        else:
            await message.edit_text(
                text=text or "",
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        return True
    except TelegramBadRequest as exc:
        # Common non-fatal errors:
        # - "message is not modified" - content is identical
        # - "there is no text in the message to edit" - already handled above
        # - "message can't be edited" - too old
        msg = str(exc)
        if "not modified" in msg.lower():
            # Content is identical - not an error
            return True
        logger.warning("safe_edit_message failed: {}", msg[:200])
        return False
    except Exception as exc:
        logger.warning("safe_edit_message unexpected error: {}", exc)
        return False


async def safe_delete_message(message: Message) -> bool:
    """Delete a message safely, ignoring errors if it doesn't exist."""
    try:
        await message.delete()
        return True
    except Exception:
        return False
