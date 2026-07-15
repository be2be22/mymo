"""
Miscellaneous helper functions used throughout the bot.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from config.settings import settings


def safe_int(value: object, default: int = 0) -> int:
    """Convert ``value`` to int safely; return ``default`` on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def is_admin(telegram_id: int) -> bool:
    """Return True if ``telegram_id`` is one of the configured admins."""
    return telegram_id in settings.admin_id_list


def extract_mymoviz_id_from_url(url: str) -> Optional[str]:
    """Extract the canonical MyMoviz content id from a URL.

    MyMoviz URLs typically look like:
        https://mymoviz.co/movie/12345-some-title
        https://mymoviz.co/_modern/series/67890-some-series
        https://mymoviz.co/12345

    The id is the last path segment (slug).
    """
    if not url:
        return None
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return None
    # Take last segment
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    return segments[-1]


def build_site_url(path: str, base: Optional[str] = None) -> str:
    """Build an absolute URL on the MyMoviz site from a relative path."""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = base or settings.classic_base_url
    if not path.startswith("/"):
        path = "/" + path
    return urljoin(base, path)


def truncate_text(text: Optional[str], max_length: int = 800) -> str:
    """Truncate ``text`` to ``max_length`` characters, appending an ellipsis."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def hash_payload(payload: str) -> str:
    """Return a short MD5 hash of a payload (used for notification dedupe)."""
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def sanitize_filename(name: str) -> str:
    """Make a string safe to use as a filename."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:64]
