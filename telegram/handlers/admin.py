"""
Admin handlers - statistics, broadcast, force-check, cache cleanup.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.cache_manager import cache
from database.models import User
from database.repositories import (
    MovieRepository,
    NotificationRepository,
    SeriesRepository,
    SubscriptionRepository,
    UserRepository,
)
from telegram.filters import is_admin_filter
from telegram.keyboards import admin_panel_kb, back_to_main_kb, confirm_kb
from utils.formatters import format_admin_stats
from utils.helpers import is_admin
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="admin")


class AdminStates(StatesGroup):
    """FSM states for admin broadcast flow."""

    waiting_for_broadcast_text = State()


# ----------------------------------------------------------------------
# Show admin panel (gated by IsAdminFilter)
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "admin:panel")
async def cb_admin_panel(callback: CallbackQuery) -> None:
    """Open the admin panel (admin-only)."""
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


# ----------------------------------------------------------------------
# Stats
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show bot statistics (admin-only)."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return

    try:
        stats = {
            "users": await UserRepository.count_all(session),
            "subscriptions": await SubscriptionRepository.count_all(session),
            "series": await SeriesRepository.count_all(session),
            "movies": await MovieRepository.count_all(session),
            "notifications": await NotificationRepository.count_all(session),
            "failed": await NotificationRepository.count_failed(session),
        }
        from telegram.safe_edit import safe_edit_message
        await safe_edit_message(
            callback.message, format_admin_stats(stats), reply_markup=admin_panel_kb()
        )
    except Exception as exc:
        logger.error("Admin stats failed: {}", exc)
        from telegram.safe_edit import safe_edit_message
        await safe_edit_message(
            callback.message,
            f"❌ خطا در دریافت آمار: <code>{exc}</code>",
            reply_markup=admin_panel_kb(),
        )
    await callback.answer()


# ----------------------------------------------------------------------
# Broadcast
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "admin:broadcast")
async def cb_admin_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Begin broadcast flow."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    from telegram.safe_edit import safe_edit_message
    await safe_edit_message(
        callback.message,
        "📢 <b>ارسال پیام همگانی</b>\n\n"
        "متن پیام را ارسال کنید (HTML مجاز است):\n\n"
        "⚠ این پیام به همه کاربران فعال ارسال خواهد شد.",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast_text)
async def handle_broadcast_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Confirm broadcast text before sending."""
    if not message.text:
        await message.answer("❌ لطفاً متن ارسال کنید.")
        return
    await state.update_data(broadcast_text=message.text)
    await state.clear()
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    # Store the text in state data
    await state.update_data(broadcast_text=message.text, awaiting_confirm=True)
    await message.answer(
        f"📝 <b>پیش‌نمایش پیام:</b>\n\n{message.text}\n\n"
        "✅ برای ارسال به همه کاربران، روی «بله» بزنید.",
        reply_markup=confirm_kb(
            yes_callback="admin:broadcast_confirm",
            no_callback="admin:panel",
        ),
    )


@router.callback_query(lambda c: c.data == "admin:broadcast_confirm")
async def cb_broadcast_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Actually send the broadcast."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ غیرمجاز", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()

    if not text:
        await callback.answer("❌ متنی ذخیره نشده بود.", show_alert=True)
        return

    # Get bot instance from dispatcher
    from main import bot  # late import to avoid circular

    user_ids = await UserRepository.list_active_ids(session)
    sent = 0
    failed = 0
    from telegram.safe_edit import safe_edit_message
    await safe_edit_message(
        callback.message,
        f"⏳ در حال ارسال به {len(user_ids)} کاربر...", reply_markup=back_to_main_kb()
    )
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, disable_web_page_preview=True)
            sent += 1
        except Exception as exc:
            failed += 1
            logger.warning("Broadcast to {} failed: {}", uid, exc)
        # Rate-limit: ~25 msgs/sec to stay under Telegram's limits
        import asyncio
        await asyncio.sleep(0.04)

    await callback.message.answer(
        f"✅ ارسال کامل شد.\n\n📤 موفق: {sent}\n❌ ناموفق: {failed}",
        reply_markup=admin_panel_kb(),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Force-check
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "admin:force_check")
async def cb_force_check(callback: CallbackQuery) -> None:
    """Trigger an immediate scheduler check (admin-only)."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return
    await callback.answer("⏳ بررسی فوری شروع شد...", show_alert=False)
    try:
        from scheduler.jobs import run_check_now, run_new_content_check
        await run_check_now()
        await run_new_content_check()
        await callback.message.answer(
            "✅ بررسی فوری انجام شد (اعلان‌ها + محتوای جدید).",
            reply_markup=admin_panel_kb(),
        )
    except Exception as exc:
        logger.error("Force check failed: {}", exc)
        await callback.message.answer(
            f"❌ خطا: <code>{exc}</code>", reply_markup=admin_panel_kb()
        )


# ----------------------------------------------------------------------
# Clear cache
# ----------------------------------------------------------------------
@router.callback_query(lambda c: c.data == "admin:clear_cache")
async def cb_clear_cache(callback: CallbackQuery) -> None:
    """Clear the entire cache."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer("⛔ این بخش فقط برای ادمین است.", show_alert=True)
        return
    n = await cache.cleanup_expired()
    await cache.clear()
    from telegram.safe_edit import safe_edit_message
    await safe_edit_message(
        callback.message,
        f"🧹 کش پاک شد (تعداد موارد حذف‌شده: {n}).",
        reply_markup=admin_panel_kb(),
    )
    await callback.answer("✅ کش پاک شد.", show_alert=False)


# ----------------------------------------------------------------------
# Hidden /admin command
# ----------------------------------------------------------------------
@router.message(lambda m: m.text and m.text.strip() == "/admin")
async def cmd_admin(message: Message) -> None:
    """Open admin panel via /admin command."""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ این دستور فقط برای ادمین‌هاست.")
        return
    await message.answer("🛠 <b>پنل مدیریت</b>", reply_markup=admin_panel_kb())
