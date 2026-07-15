"""
User-facing handlers - /start, main menu, basic info.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
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
    """Handle '🏠 خانه' callback."""
    fav_count = len(await FavoriteRepository.list_by_user(session, db_user.id))
    sub_count = len(await SubscriptionRepository.list_by_user(session, db_user.id))
    text = (
        f"📋 <b>منوی اصلی</b>\n\n"
        f"⭐ علاقه‌مندی‌های شما: {fav_count}\n"
        f"🔔 اعلان‌های فعال شما: {sub_count}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(lambda c: c.data == "about:show")
async def cb_about(callback: CallbackQuery) -> None:
    """About bot text."""
    about_text = (
        "ℹ <b>درباره ربات</b>\n\n"
        "🎬 <b>MyMoviz Notify Bot</b>\n"
        "نسخه: 1.0.0\n\n"
        "📡 منبع داده: <a href=\"https://mymoviz.co\">MyMoviz.co</a>\n"
        "⚡ تکنولوژی: Python 3.12 + Aiogram 3 + APScheduler\n"
        "🔄 بررسی خودکار: هر ۱۰ دقیقه\n\n"
        "این ربات به صورت متن‌باز توسعه داده شده است."
    )
    await callback.message.edit_text(
        about_text, reply_markup=back_to_main_kb(), disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "settings:menu")
async def cb_settings_menu(callback: CallbackQuery) -> None:
    """Open settings menu."""
    await callback.message.edit_text(
        "⚙ <b>تنظیمات</b>\n\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def cb_admin_gate(callback: CallbackQuery) -> None:
    """Gate: only allow admin callbacks."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return
    # The actual admin handlers below will handle specific admin: callbacks.
    # If none of them matched, we just open the admin panel.
    await callback.message.edit_text(
        "🛠 <b>پنل مدیریت</b>", reply_markup=admin_panel_kb()
    )
    await callback.answer()
