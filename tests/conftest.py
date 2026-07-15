"""
Pytest configuration and shared fixtures.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Make project root importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Set test environment variables BEFORE importing any project modules
os.environ.setdefault("BOT_TOKEN", "test:test_token")
os.environ.setdefault("ADMIN_IDS", "111111,222222")
os.environ.setdefault("CHANNEL_IDS", "@test_channel")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
os.environ.setdefault("CHECK_INTERVAL_MINUTES", "1")


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
