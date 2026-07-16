"""
Inline keyboards (glass-style buttons) for the bot UI.

Callback data uses short IMDb IDs (without "tt" prefix, e.g. "1375666")
to stay within Telegram's 64-byte limit. No database mapping needed
because the ID is reversible: just prepend "tt" to get the full ID.

Examples:
    d:1375666     → detail page for tt1375666 (Inception)
    d:11198330    → detail page for tt11198330 (House of the Dragon)
    fav:1375666   → toggle favorite for tt1375666
    dl:1375666    → download page for tt1375666
    sq:11198330:1 → season 1 quality selection for tt11198330
    ql:11198330:1:480p → quality "480p" links for season 1
"""

from __future__ import annotations

import re
from typing import List, Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import ContentType


# ---------------------------------------------------------------------
# ID helpers - extract short ID from various formats, resolve back
# ---------------------------------------------------------------------
def extract_imdb_id(mymoviz_id: str) -> Optional[str]:
    """Extract the IMDb ID (ttXXXXXXX) from a mymoviz_id string.

    Examples:
        "tvshows/tt11198330/House-of-the-Dragon-2022" → "tt11198330"
        "tt1375666/Inception-2010"                    → "tt1375666"
        "tt1375666"                                    → "tt1375666"
    """
    if not mymoviz_id:
        return None
    m = re.search(r"(tt\d+)", mymoviz_id)
    return m.group(1) if m else None


def make_short_id(mymoviz_id: str) -> Optional[str]:
    """Convert a mymoviz_id to a short numeric ID (without "tt" prefix).

    Returns None if no IMDb ID is found.
    """
    imdb_id = extract_imdb_id(mymoviz_id)
    if imdb_id:
        return imdb_id[2:]  # strip "tt"
    return None


def resolve_short_id(short_id: str) -> str:
    """Convert a short numeric ID back to a full IMDb ID."""
    return f"tt{short_id}"


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
        label = label[:60]
        short = make_short_id(item.get("mymoviz_id", ""))
        if short:
            builder.button(text=label, callback_data=f"d:{short}")
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
    short = make_short_id(mymoviz_id)
    if not short:
        return back_to_main_kb()

    fav_label = "❌ حذف از علاقه‌مندی" if is_favorite else "⭐ افزودن به علاقه‌مندی"
    sub_label = "❌ حذف اطلاع‌رسانی" if is_subscribed else "🔔 اطلاع بده"

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
        short = make_short_id(fav.get("mymoviz_id", ""))
        if short:
            builder.button(text=f"{icon} {title}"[:60], callback_data=f"d:{short}")
    builder.adjust(1)
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def subscriptions_list_kb(subscriptions: List[dict]) -> InlineKeyboardMarkup:
    """List of user subscriptions."""
    builder = InlineKeyboardBuilder()
    for sub in subscriptions[:15]:
        icon = "🎬" if sub.get("content_type") == "movie" else "📺"
        title = sub.get("title") or "—"
        short = make_short_id(sub.get("mymoviz_id", ""))
        if short:
            builder.button(text=f"{icon} {title}"[:60], callback_data=f"d:{short}")
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


# ---------------------------------------------------------------------
# Download flow keyboards
# ---------------------------------------------------------------------
def seasons_kb(short_id: str, seasons: list[dict]) -> InlineKeyboardMarkup:
    """Show season selection buttons for a series.

    seasons: [{"season": 1, "episodes": 10, "label": "فصل 1"}, ...]
    """
    builder = InlineKeyboardBuilder()
    for s in seasons[:15]:
        label = s.get("label", f"فصل {s['season']}")
        ep_count = s.get("episodes", "")
        btn_text = f"📺 {label}"
        if ep_count:
            btn_text += f" ({ep_count} قسمت)"
        builder.button(
            text=btn_text[:60],
            callback_data=f"sq:{short_id}:{s['season']}",
        )
    builder.adjust(1)
    builder.button(text="⬅ بازگشت", callback_data=f"d:{short_id}")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()


def qualities_kb(short_id: str, season: Optional[int], qualities: list[dict]) -> InlineKeyboardMarkup:
    """Show quality selection buttons.

    qualities: [{"quality": "480p", "format": "MP4", "size": "359 MB", "type": "dub"}, ...]
    """
    builder = InlineKeyboardBuilder()
    for q in qualities[:10]:
        quality = q.get("quality", "نامشخص")
        size = q.get("size", "")
        dtype = q.get("type", "")
        icon = "🎙" if dtype == "dub" else "📝" if dtype == "sub" else "🎬"
        btn_text = f"{icon} {quality}"
        if size:
            btn_text += f" - {size}"
        if season is not None:
            builder.button(
                text=btn_text[:60],
                callback_data=f"ql:{short_id}:{season}:{quality}",
            )
        else:
            builder.button(
                text=btn_text[:60],
                callback_data=f"ql:{short_id}:0:{quality}",
            )
    builder.adjust(1)
    if season is not None:
        builder.button(text="⬅ بازگشت به فصل‌ها", callback_data=f"dl:{short_id}")
    else:
        builder.button(text="⬅ بازگشت", callback_data=f"d:{short_id}")
    builder.button(text="🏠 خانه", callback_data="menu:main")
    return builder.as_markup()
