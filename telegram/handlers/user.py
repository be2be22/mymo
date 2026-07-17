"""
User-facing handlers - /start, main menu, basic info.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repositories import (
    FavoriteRepository,
    SubscriptionRepository,
)
from telegram.keyboards import main_menu_kb, admin_panel_kb, back_to_main_kb
from utils.helpers import is_admin
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="user")


WELCOME_TEXT = (
    "👋 <b>به ربات MyMoviz Notify خوش آمدید!</b>\n\n"
    "🎬 این ربات به شما کمک می‌کند تا فیلم‌ها و سریال‌های سایت "
    "<a href=\"https://mymoviz.co\">MyMoviz.co</a> را جستجو، مشاهده و "
    "دنبال کنید.\n\n"
    "✨ <b>امکانات:</b>\n"
    "🔎 جستجوی فیلم و سریال (فارسی و انگلیسی)\n"
    "⭐ افزودن به علاقه‌مندی‌ها\n"
    "🔔 اطلاع‌رسانی خودکار قسمت/کیفیت/دوبله جدید\n"
    "🕒 آخرین انتشارها و محبوب‌ترین‌ها\n\n"
    "از منوی زیر انتخاب کنید 👇"
)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(
    message: Message,
    session: AsyncSession,
    db_user: User,
    command: CommandObject = None,
) -> None:
    """Handle /start <content_id> deep link - show content detail directly."""
    import re
    if command and command.args:
        content_id = command.args.strip()
        if content_id.isdigit():
            # Modern numeric ID - fetch the modern page to get imdb_id
            try:
                from scrapers.manager import scraper_manager
                from utils.formatters import format_movie_info, format_series_info
                from telegram.keyboards import content_detail_kb
                from database.models import ContentType

                wait_msg = await message.answer("⏳ در حال دریافت اطلاعات...")
                detail = await scraper_manager.get_content_detail(
                    f"https://mymoviz.co/_modern/title/{content_id}", "movie"
                )
                if detail and (detail.title_fa or detail.title_en):
                    # Find imdb_id from page URL or poster URL
                    imdb_id = None
                    for url_candidate in [detail.page_url, detail.poster_url, detail.mymoviz_id]:
                        if url_candidate:
                            m = re.search(r"(tt\d+)", url_candidate)
                            if m:
                                imdb_id = m.group(1)
                                break
                    if not imdb_id and detail.mymoviz_id and detail.mymoviz_id.startswith("tt"):
                        imdb_id = detail.mymoviz_id

                    if imdb_id:
                        content_type_str = "series" if (
                            detail.episodes
                            or (detail.page_url and "/tvshows/" in detail.page_url)
                        ) else "movie"
                        ct = ContentType.SERIES if content_type_str == "series" else ContentType.MOVIE
                        if content_type_str == "series":
                            text = format_series_info(detail)
                        else:
                            text = format_movie_info(detail)
                        kb = content_detail_kb(
                            content_type=ct,
                            mymoviz_id=imdb_id,
                            site_url=detail.page_url,
                        )
                        try:
                            await wait_msg.delete()
                        except Exception:
                            pass
                        if detail.poster_url:
                            await message.answer_photo(
                                photo=detail.poster_url,
                                caption=text,
                                reply_markup=kb,
                            )
                        else:
                            await message.answer(text, reply_markup=kb, disable_web_page_preview=True)
                        return
            except Exception as exc:
                logger.warning("Deep link detail fetch failed: {}", exc)
            await message.answer(
                "❌ محتوای درخواستی یافت نشد.",
                reply_markup=main_menu_kb(),
            )
            return

    # No deep link args - show normal welcome
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(), disable_web_page_preview=True)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, db_user: User) -> None:
    """Handle /start - show welcome + main menu."""
    logger.info("/start from user_id={} (db_user_id={})",
                message.from_user.id if message.from_user else 0,
                db_user.id if db_user else None)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(), disable_web_page_preview=True)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Show main menu."""
    await message.answer("📋 <b>منوی اصلی</b>", reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Show help text."""
    help_text = (
        "📖 <b>راهنمای استفاده</b>\n\n"
        "1️⃣ روی دکمه «🔎 جستجو» بزنید و نام فیلم یا سریال را وارد کنید.\n"
        "2️⃣ از بین نتایج، مورد دلخواه را انتخاب کنید.\n"
        "3️⃣ در صفحه اطلاعات می‌توانید:\n"
        "   • ⭐ به علاقه‌مندی اضافه کنید\n"
        "   • 🔔 اطلاع‌رسانی را فعال کنید\n"
        "   • 📥 لینک دانلود را بگیرید\n"
        "   • 🌐 به سایت اصلی بروید\n\n"
        "🔔 ربات هر ۱۰ دقیقه بررسی می‌کند و در صورت تغییر، به شما اطلاع می‌دهد.\n\n"
        "💡 دستورات:\n"
        "/start - شروع\n"
        "/menu - منوی اصلی\n"
        "/help - راهنما"
    )
    await message.answer(help_text, reply_markup=back_to_main_kb())


@router.callback_query(lambda c: c.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Handle '🏠 خانه' callback - delete photo messages and send fresh text menu."""
    fav_count = len(await FavoriteRepository.list_by_user(session, db_user.id))
    sub_count = len(await SubscriptionRepository.list_by_user(session, db_user.id))
    text = (
        f"📋 <b>منوی اصلی</b>\n\n"
        f"⭐ علاقه‌مندی‌های شما: {fav_count}\n"
        f"🔔 اعلان‌های فعال شما: {sub_count}"
    )
    from telegram.safe_edit import safe_edit_message, safe_delete_message
    # If the current message is a photo, delete it and send a fresh text message.
    # This prevents old posters from lingering when user returns to main menu.
    if callback.message.photo:
        await safe_delete_message(callback.message)
        await callback.message.answer(text, reply_markup=main_menu_kb())
    else:
        await safe_edit_message(callback.message, text, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(lambda c: c.data == "about:show")
async def cb_about(callback: CallbackQuery) -> None:
    """About bot text - bot biography and feature list."""
    about_text = (
        "🎬 <b>MyMoviz Notify Bot</b>\n\n"
        "ربات فارسی برای دنبال کردن فیلم‌ها و سریال‌های سایت MyMoviz.co\n\n"
        "✨ <b>با این ربات می‌توانید:</b>\n\n"
        "🔎 <b>جستجوی فیلم و سریال</b>\n"
        "نام فارسی یا انگلیسی فیلم/سریال را بنویسید و نتایج را با پوستر، سال، امتیاز و نوع ببینید.\n\n"
        "📋 <b>صفحه اطلاعات کامل</b>\n"
        "پوستر، خلاصه داستان، ژانر، سال، امتیاز IMDb، کشور، مدت زمان، کیفیت‌ها، وضعیت دوبله و زیرنویس.\n\n"
        "📥 <b>دانلود مرحله‌ای</b>\n"
        "برای سریال‌ها: فصل → کیفیت → همه لینک‌های دانلود قسمت‌ها\n"
        "برای فیلم‌ها: کیفیت → لینک‌های دانلود مستقیم + زیرنویس‌ها\n\n"
        "⭐ <b>علاقه‌مندی‌ها</b>\n"
        "فیلم‌ها و سریال‌های دلخواه را ذخیره کنید و سریع به آن‌ها دسترسی داشته باشید.\n\n"
        "🔔 <b>اطلاع‌رسانی خودکار</b>\n"
        "برای هر فیلم یا سریال اعلان فعال کنید تا در صورت:\n"
        "  • افزودن قسمت جدید (سریال)\n"
        "  • افزودن کیفیت جدید\n"
        "  • افزودن دوبله یا زیرنویس جدید\n"
        "خودکار به شما اطلاع داده شود.\n"
        "⚠ حداکثر ۵ اعلان فعال می‌توانید داشته باشید.\n\n"
        "🕒 <b>آخرین انتشارها</b>\n"
        "جدیدترین فیلم‌ها و سریال‌های اضافه‌شده به سایت را ببینید.\n\n"
        "🔥 <b>محبوب‌ترین‌ها</b>\n"
        "پربازدیدترین فیلم‌ها و سریال‌ها را کشف کنید.\n\n"
        "📢 <b>کانال تلگرام</b>\n"
        "هر ساعت، فیلم‌ها و سریال‌های جدید سایت به‌صورت خودکار در کانال معرفی می‌شوند.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📡 منبع داده: <a href=\"https://mymoviz.co\">MyMoviz.co</a>\n"
        "⚡ تکنولوژی: Python 3.12 + Aiogram 3 + APScheduler\n"
        "🔄 بررسی اعلان‌ها: هر ۱۰ دقیقه\n"
        "🔄 بررسی محتوای جدید: هر ۱ ساعت\n"
        "━━━━━━━━━━━━━━━━"
    )
    from telegram.safe_edit import safe_edit_message
    await safe_edit_message(callback.message, about_text, reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin:panel")
async def cb_admin_gate(callback: CallbackQuery) -> None:
    """Open the admin panel (only matches admin:panel, not admin:stats etc.)."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return
    from telegram.safe_edit import safe_edit_message
    await safe_edit_message(
        callback.message,
        "🛠 <b>پنل مدیریت</b>\n\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=admin_panel_kb(),
    )
    await callback.answer()
