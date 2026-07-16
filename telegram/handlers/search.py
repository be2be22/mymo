"""
Search handlers - free-text search and result display.

Uses a per-user "searching" flag stored in Redis-like in-memory state
(kept simple here for production single-instance deployment).
"""

from __future__ import annotations

from typing import Dict

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.cache_manager import cache
from database.models import User
from scrapers.manager import scraper_manager
from telegram.keyboards import cancel_kb, search_results_kb, back_to_main_kb
from utils.formatters import format_search_result
from utils.helpers import build_site_url
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router(name="search")


class SearchStates(StatesGroup):
    """FSM states for the search flow."""

    waiting_for_query = State()


@router.callback_query(lambda c: c.data == "search:start")
async def cb_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to enter a search query."""
    await state.set_state(SearchStates.waiting_for_query)
    await callback.message.edit_text(
        "🔎 <b>جستجو</b>\n\n"
        "نام فیلم یا سریال را به فارسی یا انگلیسی وارد کنید:\n\n"
        "💡 می‌توانید فقط بخشی از نام را هم بنویسید.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(SearchStates.waiting_for_query)
async def handle_search_query(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    """Receive a search query, hit the scraper, and show results."""
    if not message.text:
        await message.answer("❌ لطفاً یک متن وارد کنید.", reply_markup=cancel_kb())
        return

    query = message.text.strip()
    if len(query) < 2:
        await message.answer(
            "❌ عبارت جستجو باید حداقل ۲ کاراکتر باشد.", reply_markup=cancel_kb()
        )
        return

    # NOTE: Do NOT clear the state yet - keep it as waiting_for_query so the
    # user can search again if no results are found or if they want to try
    # a different query. State will be cleared when user clicks a result,
    # presses Cancel, or returns to main menu.

    cache_key = f"search:{query.lower()}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.info("Search cache hit for '{}'", query)
        await _send_search_results(message, cached, query)
        return

    wait_msg = await message.answer("⏳ در حال جستجو...")

    try:
        results = await scraper_manager.search(query)
    except Exception as exc:
        logger.error("Search failed for '{}': {}", query, exc)
        await wait_msg.edit_text(
            "❌ خطا در جستجو. لطفاً دوباره تلاش کنید یا نام دیگری وارد کنید.",
            reply_markup=cancel_kb(),
        )
        return

    if not results:
        # Keep the state as waiting_for_query so user can search again
        await wait_msg.edit_text(
            f"🔍 نتیجه‌ای برای «<b>{query}</b>» یافت نشد.\n"
            "💡 نام دیگری وارد کنید یا با نام انگلیسی امتحان کنید:",
            reply_markup=cancel_kb(),
        )
        return

    # Now that we have results, clear the state
    await state.clear()

    # Convert to plain dicts for cache + keyboard
    items: list[dict] = []
    for r in results[:15]:
        items.append(
            {
                "title_fa": r.title_fa,
                "title_en": r.title_en,
                "year": r.year,
                "imdb_rating": r.imdb_rating,
                "content_type": r.content_type,
                "poster_url": r.poster_url,
                "page_url": r.page_url,
                "mymoviz_id": r.mymoviz_id,
            }
        )

    await cache.set(cache_key, items)
    await _send_search_results(message, items, query, wait_msg)


async def _send_search_results(
    message: Message,
    items: list[dict],
    query: str,
    wait_msg: "Message | None" = None,
) -> None:
    """Render search results to the user."""
    text_lines = [f"🔎 <b>نتایج جستجو برای «{query}»</b>\n"]
    for idx, item in enumerate(items, start=1):
        text_lines.append(f"<b>{idx}.</b> " + format_search_result(item))
        text_lines.append("➖➖➖➖➖➖➖➖➖➖")
    text = "\n".join(text_lines)[:4000]

    kb = search_results_kb(items)
    if wait_msg is not None:
        try:
            await wait_msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            await message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(lambda c: c.data == "cancel:yes")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel current operation."""
    await state.clear()
    await callback.message.edit_text(
        "❌ عملیات لغو شد.", reply_markup=back_to_main_kb()
    )
    await callback.answer()


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    """/search <query> shortcut."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "💡 استفاده: <code>/search &lt;نام فیلم یا سریال&gt;</code>",
            reply_markup=back_to_main_kb(),
        )
        return
    await state.set_state(SearchStates.waiting_for_query)
    fake = await message.answer("⏳ در حال جستجو...")
    await handle_search_query(
        type("M", (), {"text": parts[1], "answer": message.answer, "from_user": message.from_user})(),
        state,
        None,  # type: ignore
        None,  # type: ignore
    )
    # Simpler: just send the search handler manually
    # But because aiogram's DI relies on proper objects, instruct the user:
    await fake.delete()
