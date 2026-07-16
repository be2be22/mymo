"""
Inline keyboards (glass-style buttons) for the bot UI.

All keyboards use ``InlineKeyboardMarkup`` with concise Persian labels and
emoji icons. Callback data is kept short to stay within Telegram's 64-byte
limit. Long ``mymoviz_id`` values (e.g. ``tvshows/tt43357366/The-Apartment-Job-2026``)
are replaced with a short 8-char MD5 hash stored in the ``callback_mappings``
database table, so the mapping survives bot restarts.
"""

from __future__ import annotations

from typing import List, Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ContentType
from database.repositories import CallbackMappingRepository


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


async def search_results_kb(results: List[dict], session: AsyncSession) -> InlineKeyboardMarkup:
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
        # Use DB-backed short key to keep callback_data under 64 bytes
        short = await CallbackMappingRepository.get_or_create(session, ct, mymoviz_id)
        builder.button(
            text=label,
            callback_data=f"d:{short}",
        )
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


async def content_detail_kb(
    content_type: ContentType,
    mymoviz_id: str,
    session: AsyncSession,
    site_url: Optional[str] = None,
    is_favorite: bool = False,
    is_subscribed: bool = False,
) -> InlineKeyboardMarkup:
    """Detail-page action buttons."""
    builder = InlineKeyboardBuilder()

    fav_label = "❌ حذف از علاقه‌مندی" if is_favorite else "⭐ افزودن به علاقه‌مندی"
    sub_label = "❌ حذف اطلاع‌رسانی" if is_subscribed else "🔔 اطلاع بده"

    # Use DB-backed short key for all callbacks to stay under 64 bytes
    short = await CallbackMappingRepository.get_or_create(
        session, content_type.value, mymoviz_id
    )
    builder.button(text=fav_label, callback_data=f"fav:{short}")
    builder.button(text=sub_label, callback_data=f"sub:{short}")
    builder.button(text="📥 دانلود", callback_data=f"dl:{short}")
    if site_url:
        builder.button(text="🌐 مشاهده سایت", url=site_url)
    builder.button(text="⬅ بازگشت", callback_data="search:start")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    builder.adjust(2, 1, 1, 2)
    return builder.as_markup()


async def favorites_list_kb(favorites: List[dict], session: AsyncSession) -> InlineKeyboardMarkup:
    """List of user favorites as clickable rows."""
    builder = InlineKeyboardBuilder()
    for fav in favorites[:15]:
        icon = "🎬" if fav.get("content_type") == "movie" else "📺"
        title = fav.get("title") or "—"
        ct = fav.get("content_type", "movie")
        short = await CallbackMappingRepository.get_or_create(session, ct, fav.get("mymoviz_id", ""))
        builder.button(
            text=f"{icon} {title}"[:60],
            callback_data=f"d:{short}",
        )
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


async def subscriptions_list_kb(subscriptions: List[dict], session: AsyncSession) -> InlineKeyboardMarkup:
    """List of user subscriptions."""
    builder = InlineKeyboardBuilder()
    for sub in subscriptions[:15]:
        icon = "🎬" if sub.get("content_type") == "movie" else "📺"
        title = sub.get("title") or "—"
        ct = sub.get("content_type", "movie")
        short = await CallbackMappingRepository.get_or_create(session, ct, sub.get("mymoviz_id", ""))
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
