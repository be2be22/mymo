"""
Message formatters for Persian (RTL) Telegram messages.

All functions return strings already wrapped for Telegram HTML parse mode
when needed. Emojis are used to make the messages visually friendly.
"""

from __future__ import annotations

from typing import Any, Optional

from database.models import ContentType, NotificationType, Episode, Movie, Series
from utils.helpers import truncate_text


# ----------------------------------------------------------------------
# Search results
# ----------------------------------------------------------------------
def format_search_result(item: dict) -> str:
    """Format a single search-result row.

    Expected keys: title_fa, title_en, year, imdb_rating, content_type, poster_url
    """
    title_fa = item.get("title_fa") or "—"
    title_en = item.get("title_en") or ""
    year = item.get("year") or "—"
    rating = item.get("imdb_rating")
    content_type = item.get("content_type", "")

    icon = "🎬" if content_type == "movie" else "📺" if content_type == "series" else "🎞"

    rating_str = f"⭐ {rating}" if rating else "⭐ —"

    parts = [f"{icon} <b>{title_fa}</b>"]
    if title_en:
        parts.append(f"<i>{title_en}</i>")
    parts.append(f"📅 سال: {year}  |  {rating_str}")
    return "\n".join(parts)


# ----------------------------------------------------------------------
# Movie info
# ----------------------------------------------------------------------
def format_movie_info(movie: Movie, verbose: bool = True) -> str:
    """Build a full info-card message for a movie."""
    lines = [f"🎬 <b>{movie.title_fa or movie.title_en or 'فیلم'}</b>"]
    if movie.title_en and movie.title_fa:
        lines.append(f"<i>{movie.title_en}</i>")
    lines.append("")
    if movie.year:
        lines.append(f"📅 <b>سال:</b> {movie.year}")
    if movie.imdb_rating is not None:
        lines.append(f"⭐ <b>امتیاز IMDb:</b> {movie.imdb_rating}")
    if movie.genres:
        lines.append(f"🎭 <b>ژانر:</b> {movie.genres}")
    if movie.country:
        lines.append(f"🌍 <b>کشور:</b> {movie.country}")
    if movie.duration:
        lines.append(f"⏱ <b>مدت:</b> {movie.duration}")
    if movie.qualities:
        lines.append(f"🎥 <b>کیفیت‌ها:</b> {movie.qualities}")
    lines.append(
        f"🎙 <b>دوبله:</b> {'✅ بله' if movie.has_dubbing else '❌ خیر'}  |  "
        f"📝 <b>زیرنویس:</b> {'✅ بله' if movie.has_subtitle else '❌ خیر'}"
    )
    if verbose and movie.summary:
        lines.append("")
        lines.append(f"📖 <b>خلاصه:</b>\n{truncate_text(movie.summary, 600)}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Series info
# ----------------------------------------------------------------------
def format_series_info(series: Series, latest_episode: Optional[Episode] = None) -> str:
    """Build a full info-card message for a series."""
    lines = [f"📺 <b>{series.title_fa or series.title_en or 'سریال'}</b>"]
    if series.title_en and series.title_fa:
        lines.append(f"<i>{series.title_en}</i>")
    lines.append("")
    if series.year:
        lines.append(f"📅 <b>سال:</b> {series.year}")
    if series.imdb_rating is not None:
        lines.append(f"⭐ <b>امتیاز IMDb:</b> {series.imdb_rating}")
    if series.genres:
        lines.append(f"🎭 <b>ژانر:</b> {series.genres}")
    if series.country:
        lines.append(f"🌍 <b>کشور:</b> {series.country}")
    if series.duration:
        lines.append(f"⏱ <b>مدت:</b> {series.duration}")
    if series.qualities:
        lines.append(f"🎥 <b>کیفیت‌ها:</b> {series.qualities}")
    lines.append(
        f"🎙 <b>دوبله:</b> {'✅ بله' if series.has_dubbing else '❌ خیر'}  |  "
        f"📝 <b>زیرنویس:</b> {'✅ بله' if series.has_subtitle else '❌ خیر'}"
    )
    if latest_episode:
        lines.append(f"🆕 <b>آخرین قسمت:</b> {format_episode_label(latest_episode)}")
    if series.summary:
        lines.append("")
        lines.append(f"📖 <b>خلاصه:</b>\n{truncate_text(series.summary, 600)}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Episode label
# ----------------------------------------------------------------------
def format_episode_label(ep: Episode) -> str:
    """Return a human-readable label for an episode (e.g. 'فصل ۲ قسمت ۵')."""
    season = ep.season if ep.season is not None else "?"
    episode = ep.episode if ep.episode is not None else "?"
    label = f"فصل {season} قسمت {episode}"
    if ep.title:
        label += f" - {ep.title}"
    return label


# ----------------------------------------------------------------------
# Notification messages
# ----------------------------------------------------------------------
def format_notification_message(
    content_type: ContentType,
    notification_type: NotificationType,
    title: str,
    extra: Optional[str] = None,
    site_url: Optional[str] = None,
) -> str:
    """Build a broadcast notification message for channels/users."""
    icon_map = {
        NotificationType.NEW_EPISODE: "🆕",
        NotificationType.NEW_QUALITY: "🎥",
        NotificationType.NEW_DUBBING: "🎙",
        NotificationType.NEW_SUBTITLE: "📝",
        NotificationType.NEW_CONTENT: "✨",
    }
    label_map = {
        NotificationType.NEW_EPISODE: "قسمت جدید اضافه شد",
        NotificationType.NEW_QUALITY: "کیفیت جدید اضافه شد",
        NotificationType.NEW_DUBBING: "دوبله جدید اضافه شد",
        NotificationType.NEW_SUBTITLE: "زیرنویس جدید اضافه شد",
        NotificationType.NEW_CONTENT: "محتوای جدید اضافه شد",
    }
    content_icon = "🎬" if content_type == ContentType.MOVIE else "📺"
    content_label = "فیلم" if content_type == ContentType.MOVIE else "سریال"

    lines = [
        f"{icon_map[notification_type]} <b>{label_map[notification_type]}</b>",
        "",
        f"{content_icon} <b>{title}</b>",
        f"📦 نوع: {content_label}",
    ]
    if extra:
        lines.append(f"ℹ {extra}")
    if site_url:
        lines.append("")
        lines.append(f'🌐 <a href="{site_url}">مشاهده در سایت</a>')
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Admin stats
# ----------------------------------------------------------------------
def format_admin_stats(stats: dict) -> str:
    """Format admin panel statistics into a Persian message."""
    return (
        "📊 <b>آمار ربات</b>\n\n"
        f"👥 <b>کاربران:</b> {stats.get('users', 0)}\n"
        f"🔔 <b>اعلان‌های فعال:</b> {stats.get('subscriptions', 0)}\n"
        f"📺 <b>سریال‌ها:</b> {stats.get('series', 0)}\n"
        f"🎬 <b>فیلم‌ها:</b> {stats.get('movies', 0)}\n"
        f"📤 <b>کل اعلان‌ها:</b> {stats.get('notifications', 0)}\n"
        f"❌ <b>خطاهای ثبت شده:</b> {stats.get('failed', 0)}"
    )
