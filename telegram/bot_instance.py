"""
Global bot instance holder.

This module avoids circular imports between main.py and scheduler/jobs.py.
main.py sets the bot instance at startup, and other modules read it via
``from telegram.bot_instance import bot_instance``.
"""

from __future__ import annotations

from typing import Optional

# This will be set by main.py at startup
bot_instance = None


def set_bot(bot) -> None:
    """Set the global bot instance."""
    global bot_instance
    bot_instance = bot


def get_bot():
    """Return the global bot instance, or None if not set yet."""
    return bot_instance
