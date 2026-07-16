"""
Inline keyboards (glass-style buttons) for the bot UI.

All keyboards use ``InlineKeyboardMarkup`` with concise Persian labels and
emoji icons. Callback data is kept short to stay within Telegram's 64-byte
limit. Long ``mymoviz_id`` values (e.g. ``tvshows/tt43357366/The-Apartment-Job-2026``)
are replaced with a short MD5 hash, and the mapping is stored in
``_ID_MAP`` so handlers can recover the original ID.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import ContentType


# ---------------------------------------------------------------------
# Short ID mapping - maps short hash -> full mymoviz_id + content_type
# Telegram callback_data is limited to 64 bytes, so we cannot embed the
# full mymoviz_id (which can be 40+ chars) in the callback_data.
# Instead, we hash it to 8 chars and store the mapping here.
# ---------------------------------------------------------------------
_ID_MAP: Dict[str, tuple[str, str]] = {}  # short_key -> (content_type, mymoviz_id)
_MAX_MAP_SIZE = 5000  # prevent unbounded growth


def make_short_key(content_type: str, mymoviz_id: str) -> str:
    """Generate a short 8-char key for a content item and store the mapping."""
    raw = f"{content_type}:{mymoviz_id}"
    short = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    _ID_MAP[short] = (content_type, mymoviz_id)
    # Evict oldest entries if map is too large
    if len(_ID_MAP) > _MAX_MAP_SIZE:
        # Remove ~10% of entries (oldest inserted)
        keys_to_remove = list(_ID_MAP.keys())[: _MAX_MAP_SIZE // 10]
        for k in keys_to_remove:
            _ID_MAP.pop(k, None)
    return short


def resolve_short_key(short_key: str) -> Optional[tuple[str, str]]:
    """Resolve a short key back to (content_type, mymoviz_id)."""
    return _ID_MAP.get(short_key)


def main_menu_kb() -> InlineKeyboardMarkup:
    """Glass-style main menu with 8 buttons in a 2-column grid."""
    builder = InlineKeyboardBuilder()
    buttons = [
        ("🔎 جستجو", "search:start"),
        ("🎬 فیلم‌ها", "list:movies"),
        ("📺 سریال‌ها", "list:series"),
        ("⭐ علاقه‌مندی‌ها", "favorites:list"),
        ("🔔 اطلاع‌رسانی‌ها", "subscriptions:list"),
        ("🕒 آخرین انتشارها", "list:latest"),
        ("🔥 محبوب‌ترین‌ها", "list:popular"),
        ("📊 وضعیت دانلودها", "downloads:status"),
        ("⚙ تنظیمات", "settings:menu"),
        ("ℹ درباره ربات", "about:show"),
    ]
    for text, callback in buttons:
        builder.button(text=text, callback_data=callback)
    builder.adjust(2, 2, 2, 2, 2)
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    """Single '🏠 خانه' button to return to main menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Cancel button used inside conversational flows."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ لغو", callback_data="cancel:yes")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def search_results_kb(results: List[dict]) -> InlineKeyboardMarkup:
    """Paginated list of search results as inline buttons."""
    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(results[:15]):
        icon = "🎬" if item.get("content_type") == "movie" else "📺"
        title = item.get("title_fa") or item.get("title_en") or "—"
        year = item.get("year") or ""
        label = f"{icon} {title}"
        if year:
            label += f" ({year})"
        # Truncate to fit Telegram's button label length limit
        label = label[:60]
        mymoviz_id = item.get("mymoviz_id") or ""
        ct = item.get("content_type", "movie")
        # Use short key to keep callback_data under 64 bytes
        short = make_short_key(ct, mymoviz_id)
        builder.button(
            text=label,
            callback_data=f"d:{short}",
        )
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def content_detail_kb(
    content_type: ContentType,
    mymoviz_id: str,
    site_url: Optional[str] = None,
    is_favorite: bool = False,
    is_subscribed: bool = False,
) -> InlineKeyboardMarkup:
    """Detail-page action buttons."""
    builder = InlineKeyboardBuilder()

    fav_label = "❌ حذف از علاقه‌مندی" if is_favorite else "⭐ افزودن به علاقه‌مندی"
    sub_label = "❌ حذف اطلاع‌رسانی" if is_subscribed else "🔔 اطلاع بده"

    # Use short key for all callbacks to stay under 64 bytes
    short = make_short_key(content_type.value, mymoviz_id)
    builder.button(text=fav_label, callback_data=f"fav:{short}")
    builder.button(text=sub_label, callback_data=f"sub:{short}")
    builder.button(text="📥 دانلود", callback_data=f"dl:{short}")
    if site_url:
        builder.button(text="🌐 مشاهده سایت", url=site_url)
    builder.button(text="⬅ بازگشت", callback_data="search:start")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    builder.adjust(2, 1, 1, 2)
    return builder.as_markup()


def favorites_list_kb(favorites: List[dict]) -> InlineKeyboardMarkup:
    """List of user favorites as clickable rows."""
    builder = InlineKeyboardBuilder()
    for fav in favorites[:15]:
        icon = "🎬" if fav.get("content_type") == "movie" else "📺"
        title = fav.get("title") or "—"
        ct = fav.get("content_type", "movie")
        short = make_short_key(ct, fav.get("mymoviz_id", ""))
        builder.button(
            text=f"{icon} {title}"[:60],
            callback_data=f"d:{short}",
        )
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def subscriptions_list_kb(subscriptions: List[dict]) -> InlineKeyboardMarkup:
    """List of user subscriptions."""
    builder = InlineKeyboardBuilder()
    for sub in subscriptions[:15]:
        icon = "🎬" if sub.get("content_type") == "movie" else "📺"
        title = sub.get("title") or "—"
        ct = sub.get("content_type", "movie")
        short = make_short_key(ct, sub.get("mymoviz_id", ""))
        builder.button(
            text=f"{icon} {title}"[:60],
            callback_data=f"d:{short}",
        )
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def settings_kb(language: str = "fa") -> InlineKeyboardMarkup:
    """Settings menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 تغییر زبان", callback_data="settings:language")
    builder.button(text="🔕 سکوت اعلان‌ها", callback_data="settings:mute")
    builder.button(text="🗑 پاک کردن علاقه‌مندی‌ها", callback_data="settings:clear_favs")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    """Admin-only control panel."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 آمار ربات", callback_data="admin:stats")
    builder.button(text="📢 ارسال پیام همگانی", callback_data="admin:broadcast")
    builder.button(text="🔄 بررسی فوری", callback_data="admin:force_check")
    builder.button(text="🧹 پاکسازی کش", callback_data="admin:clear_cache")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    builder.adjust(1, 1, 1, 1, 1)
    return builder.as_markup()


def confirm_kb(yes_callback: str, no_callback: str = "menu:main") -> InlineKeyboardMarkup:
    """Yes/No confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ بله", callback_data=yes_callback)
    builder.button(text="❌ خیر", callback_data=no_callback)
    return builder.as_markup()


def notification_kb(site_url: str) -> InlineKeyboardMarkup:
    """Inline buttons appended to broadcast notification messages."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 مشاهده در سایت", url=site_url)
    return builder.as_markup()
