"""
Loguru-based logging setup.

Provides:
* ``get_logger(name)`` - returns a logger pre-configured with stdout + file sinks
* Logs are written to ``logs/bot.log`` and rotated daily
"""

from __future__ import annotations

import os
import sys
from typing import Any

from loguru import logger as _logger

from config.settings import settings


def _configure_default_logger() -> Any:
    """Configure loguru sinks (console + rotating file)."""
    _logger.remove()

    log_level = settings.log_level.upper()
    os.makedirs(settings.log_dir, exist_ok=True)

    # Console sink - colorful, human-friendly
    _logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=settings.debug,
    )

    # File sink - JSON-ish, rotating
    _logger.add(
        os.path.join(settings.log_dir, "bot.log"),
        level=log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        backtrace=True,
        diagnose=settings.debug,
    )

    # Error-only sink
    _logger.add(
        os.path.join(settings.log_dir, "errors.log"),
        level="ERROR",
        rotation="5 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        backtrace=True,
        diagnose=True,
    )

    return _logger


# Configure once at import time
logger = _configure_default_logger()


def get_logger(name: str) -> Any:
    """Return a bound logger with the given module name."""
    return logger.bind(name=name)
