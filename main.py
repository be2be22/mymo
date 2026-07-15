"""
MyMoviz Notify Bot - Application entry point.

This module:
1. Loads configuration from .env
2. Initializes the database (creating tables if needed)
3. Initializes the HTTP client and scrapers
4. Sets up the Aiogram dispatcher + handlers
5. Starts APScheduler
6. Starts the bot via long-polling OR webhook (based on settings)

Run locally:
    python main.py

Run in production:
    docker compose up -d
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress

# Try to use uvloop on POSIX for better performance
if sys.platform != "win32":
    with suppress(ImportError):
        import uvloop

        uvloop.install()

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from api.client import http_client
from cache.cache_manager import cache
from config.settings import settings, ensure_data_dir
from database.database import db_manager, init_db
from scheduler.jobs import run_check_now, setup_scheduler, shutdown_scheduler
from scrapers.manager import scraper_manager
from telegram.dispatcher import setup_dispatcher
from utils.logger import get_logger

logger = get_logger(__name__)


# Module-level bot instance - other modules import it via `from main import bot`
bot: Bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = setup_dispatcher(bot)
scheduler = setup_scheduler()


# ----------------------------------------------------------------------
# Startup / Shutdown hooks
# ----------------------------------------------------------------------
async def on_startup() -> None:
    """Initialize all subsystems before polling starts."""
    logger.info("🚀 Starting MyMoviz Notify Bot...")
    ensure_data_dir()

    # Database
    await init_db()

    # HTTP client + scrapers
    await http_client.init()
    await scraper_manager.health_check()

    # Scheduler
    scheduler.start()
    logger.info("Scheduler started.")

    # Set bot commands
    commands = [
        BotCommand(command="start", description="شروع کار با ربات"),
        BotCommand(command="menu", description="نمایش منوی اصلی"),
        BotCommand(command="help", description="راهنمای استفاده"),
        BotCommand(command="search", description="جستجوی فیلم یا سریال"),
        BotCommand(command="admin", description="پنل مدیریت (فقط ادمین)"),
    ]
    with suppress(Exception):
        await bot.set_my_commands(commands)

    logger.info("✅ Bot started successfully. Use /start in Telegram.")


async def on_shutdown() -> None:
    """Graceful shutdown."""
    logger.info("🛑 Shutting down...")
    await shutdown_scheduler()
    await http_client.close()
    await db_manager.dispose()
    await bot.session.close()
    logger.info("👋 Bye!")


# ----------------------------------------------------------------------
# Polling / Webhook
# ----------------------------------------------------------------------
async def start_polling() -> None:
    """Start the bot in long-polling mode."""
    await on_startup()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()


async def start_webhook() -> None:
    """Start the bot in webhook mode (production / Railway)."""
    await on_startup()
    webhook_url = f"{settings.webhook_url}{settings.webhook_path}"
    try:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=settings.webhook_port)
        await site.start()
        logger.info("Webhook listening on port {}", settings.webhook_port)
        # Run forever
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await on_shutdown()


def main() -> None:
    """Synchronous entry point."""
    if not settings.bot_token or settings.bot_token == "123456789:AAEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX":
        logger.error(
            "BOT_TOKEN is not set! Copy .env.example to .env and fill in real values."
        )
        sys.exit(1)

    try:
        if settings.use_webhook:
            asyncio.run(start_webhook())
        else:
            asyncio.run(start_polling())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as exc:
        logger.exception("Fatal error: {}", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
