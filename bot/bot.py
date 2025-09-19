# bot.py
# -*- coding: utf-8 -*-
import os
import sys
import django
import asyncio
from dotenv import load_dotenv
from typing import List, Optional
from html import escape


# ---------------------------
# Django setup
# ---------------------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "linguaglow.settings")
load_dotenv()
django.setup()

# ---------------------------
# Models
# ---------------------------
from users.models import CustomUser, TelegramAuthToken, TelegramMetrics
from hub.models import Lesson, LessonPublicData

# ---------------------------
# aiogram imports & config
# ---------------------------
from aiohttp import ClientTimeout
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    Message,
    CallbackQuery,
    InputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError
from asgiref.sync import sync_to_async
from django.db.models import Q

# ---------------------------
# Config
# ---------------------------
API_TOKEN = os.getenv("TG_API_TOKEN", "8308279541:AAEsAfiOcgQaHLZlrZRlSc2X2uvZ1TKu6zY")
# увеличенный таймаут для aiohttp
session = AiohttpSession(timeout=ClientTimeout(total=60))
bot = Bot(token=API_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ---------------------------
# ORM helpers (sync wrappers)
# ---------------------------
def _get_token_sync(token_value: str):
    try:
        return TelegramAuthToken.objects.select_related("user").get(token=token_value)
    except TelegramAuthToken.DoesNotExist:
        return None

def _mark_token_used_sync(token_pk):
    token = TelegramAuthToken.objects.get(pk=token_pk)
    token.used = True
    token.save(update_fields=["used"])
    return True

get_token = sync_to_async(_get_token_sync, thread_sensitive=True)
mark_token_used = sync_to_async(_mark_token_used_sync, thread_sensitive=True)
create_metrics = sync_to_async(TelegramMetrics.objects.create, thread_sensitive=True)

@sync_to_async
def save_metrics_update(metrics_obj, **kwargs):
    for k, v in kwargs.items():
        setattr(metrics_obj, k, v)
    metrics_obj.save()
    return metrics_obj

@sync_to_async
def fetch_or_create_metrics(tg_id: int, tg_username: Optional[str]):
    obj = TelegramMetrics.objects.filter(telegram_id=tg_id).first()
    if not obj:
        obj = TelegramMetrics.objects.create(
            telegram_id=tg_id,
            telegram_username=tg_username,
            pdf_downloaded=0,
            generation_requests=0,
        )
    return obj

# ---------------------------
# Search utility
# ---------------------------
@sync_to_async
def find_lessons_by_filters(levels: List[str],
                            audience_keyword: Optional[str],
                            textbook_keyword: Optional[str]):
    """
    Ищем подходящие уроки по уровням и (опционально) по учебнику (в имени урока).
    Возвращаем список LessonPublicData.
    В логах — печатаем результаты после каждого фильтра.
    """
    all_qs = LessonPublicData.objects.select_related("lesson").all()
    print(f"[DEBUG] Всего уроков в базе: {all_qs.count()}")
    print(f"[DEBUG] Все уроки (names): {[l.lesson.name for l in all_qs]}")

    qs = all_qs.filter(level__in=levels)
    print(f"[DEBUG] После фильтра по levels={levels}: {qs.count()}")
    print(f"[DEBUG] Уроки после levels: {[l.lesson.name for l in qs]}")

    if textbook_keyword and textbook_keyword.lower() not in ("нет", "no"):
        qs = qs.filter(lesson__name__icontains=textbook_keyword)
        print(f"[DEBUG] После фильтра по textbook='{textbook_keyword}': {qs.count()}")
        print(f"[DEBUG] Уроки после textbook: {[l.lesson.name for l in qs]}")

    qs = qs.filter(pdf_file__isnull=False).order_by("-lesson__created_at")
    print(f"[DEBUG] После фильтра по pdf_file: {qs.count()}")
    print(f"[DEBUG] Итоговые уроки (with pdf): {[l.lesson.name for l in qs]}")

    return list(qs)

@sync_to_async
def list_all_public_lessons(limit: int = 50):
    qs = LessonPublicData.objects.select_related("lesson").filter(pdf_file__isnull=False).order_by("-lesson__created_at")[:limit]
    return list(qs)

# ---------------------------
# Constants & states
# ---------------------------
PUBLIC_LEVEL_CHOICES_KEYS = ["A1", "A2", "B1", "B2", "C1"]

class OnboardingStates(StatesGroup):
    levels = State()
    audience = State()
    textbook = State()
    done = State()

# ---------------------------
# Keyboards (aiogram v3) -- builder pattern
# ---------------------------
def levels_keyboard(selected: Optional[List[str]] = None) -> object:
    selected = set(selected or [])
    builder = InlineKeyboardBuilder()
    for lvl in PUBLIC_LEVEL_CHOICES_KEYS:
        label = f"[✓] {lvl}" if lvl in selected else lvl
        builder.button(text=label, callback_data=f"level_toggle:{lvl}")
    builder.adjust(3)
    # navigation row
    builder.button(text="⬅ Назад", callback_data="back:levels", row=1)
    builder.button(text="Готово ✅", callback_data="levels_done", row=1)
    builder.button(text="Сбросить", callback_data="levels_reset", row=1)
    return builder.as_markup()

def audience_keyboard() -> object:
    # Разделение классов по группам 1-4, 5-7, 8-11
    builder = InlineKeyboardBuilder()
    builder.button(text="Классы 1–4", callback_data="aud:school_1_4")
    builder.button(text="Классы 5–7", callback_data="aud:school_5_7")
    builder.button(text="Классы 8–11", callback_data="aud:school_8_11")
    builder.button(text="Университет", callback_data="aud:university")
    builder.button(text="Работа / Business", callback_data="aud:work")
    builder.adjust(1)
    builder.button(text="⬅ Назад", callback_data="back:audience")
    return builder.as_markup()

def textbook_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(text="Spotlight", callback_data="tb:Spotlight")
    builder.button(text="Starlight", callback_data="tb:Starlight")
    builder.button(text="Нет", callback_data="tb:Нет")
    builder.adjust(2)
    builder.button(text="⬅ Назад", callback_data="back:textbook")
    return builder.as_markup()

def result_keyboard(lesson_public_id: Optional[str] = None, pdf_url: Optional[str] = None) -> object:
    builder = InlineKeyboardBuilder()
    if pdf_url:
        builder.button(text="📥 Скачать PDF", url=pdf_url)
    if lesson_public_id:
        builder.button(text="Еще похожие", callback_data=f"action:more_like_this:{lesson_public_id}")
    builder.button(text="Посмотреть все материалы", callback_data="action:view_all")
    builder.button(text="Создать свой урок (2 клика)", url="https://linguaglow.ru/")
    builder.adjust(1)
    builder.button(text="⬅ Вернуться в меню", callback_data="back:to_menu")
    return builder.as_markup()

def simple_menu_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(text="Начать подбор материалов", callback_data="menu:start_onboarding")
    builder.button(text="Посмотреть все доступные материалы", callback_data="action:view_all")
    builder.adjust(1)
    return builder.as_markup()

# ---------------------------
# Helper: format lesson info
# ---------------------------
def format_lesson_short(lp: LessonPublicData) -> str:
    has_pdf = bool(lp.pdf_file and lp.pdf_file.name)
    url = f"https://linguaglow.ru/lesson/{lp.link_name or lp.lesson.id}"
    return f"• {lp.lesson.name} — уровень {lp.level} — {'PDF' if has_pdf else 'нет PDF'} — {url}"

# ---------------------------
# Clear start / binding
# ---------------------------
@dp.message(lambda m: m.text and m.text.startswith("/start"))
async def start(message: Message):
    """
    /start <TOKEN>  — привязка аккаунта
    После успешной привязки пользователь получит инструкцию и кнопку 'Начать'.
    """
    tg_id = message.from_user.id
    tg_username = getattr(message.from_user, "username", None)

    # ensure metrics
    metrics = await fetch_or_create_metrics(tg_id, tg_username)

    args = message.text.split(maxsplit=1)
    token_arg = args[1].strip() if len(args) > 1 else None
    if not token_arg:
        await message.answer(
            "Привет 👋\nЧтобы привязать аккаунт, зайдите через сайт и запустите бота с токеном:\n\n"
            "/start YOUR_TOKEN\n\n"
            "Или просто нажмите кнопку ниже, чтобы начать подбор материалов (если уже привязали аккаунт на сайте).",
            reply_markup=simple_menu_keyboard()
        )
        return

    token = escape(token_arg)
    if not token or not getattr(token, "is_valid", lambda: True)():
        await message.answer("❌ Неверный или устаревший токен. Проверьте его на сайте.")
        return

    user = token.user
    try:
        # привязываем пользователя к метрикам
        metrics.user = user
        metrics.telegram_username = tg_username
        await sync_to_async(metrics.save, thread_sensitive=True)()
        await mark_token_used(token.pk)
        await message.answer("✅ Telegram успешно привязан к аккаунту!\nНажмите «Начать подбор материалов» ↓", reply_markup=simple_menu_keyboard())
    except Exception as e:
        print(f"[ERROR] bind error: {e}")
        await message.answer("❌ Ошибка при привязке аккаунта. Попробуйте позже.")

# ---------------------------
# Fallback / help message
# ---------------------------
@dp.message(lambda m: m.text and m.text.lower() in ("help", "помощь"))
async def help_msg(message: Message):
    await message.answer(
        "Напишите /start <TOKEN> чтобы привязать аккаунт.\n"
        "Или нажмите кнопку «Начать подбор материалов» чтобы пройти быстрый онбординг и получить PDF-ы.",
        reply_markup=simple_menu_keyboard()
    )

@dp.message()
async def fallback(message: Message):
    await message.answer("Я вас не понял. Нажмите «Начать подбор материалов» или напишите /start <TOKEN>.", reply_markup=simple_menu_keyboard())

# ---------------------------
# Onboarding flow
# ---------------------------
@dp.callback_query(lambda c: c.data and c.data == "menu:start_onboarding")
async def cb_menu_start(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    tg_username = getattr(callback.from_user, "username", None)
    metrics = await fetch_or_create_metrics(tg_id, tg_username)
    await state.update_data(metrics_id=metrics.id)
    await state.update_data(selected_levels=[])
    await state.set_state(OnboardingStates.levels)
    await callback.message.answer("Шаг 1/3 — выберите уровни (можно несколько):", reply_markup=levels_keyboard([]))
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("level_toggle:"))
async def cb_toggle_level(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: List[str] = data.get("selected_levels", [])
    _, lvl = callback.data.split(":", 1)
    if lvl in selected:
        selected.remove(lvl)
    else:
        selected.append(lvl)
    await state.update_data(selected_levels=selected)
    try:
        await callback.message.edit_text("Шаг 1/3 — выберите уровни (можно несколько):", reply_markup=levels_keyboard(selected))
    except Exception:
        await callback.message.answer("Уровень отмечен: " + ", ".join(selected))
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data == "levels_done")
async def cb_levels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: List[str] = data.get("selected_levels", [])
    if not selected:
        await callback.answer("Выберите хотя бы один уровень.", show_alert=True)
        return
    await state.update_data(selected_levels=selected)
    await state.set_state(OnboardingStates.audience)
    await callback.message.edit_text("Шаг 2/3 — выберите целевую аудиторию:", reply_markup=audience_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data == "levels_reset")
async def cb_levels_reset(callback: CallbackQuery, state: FSMContext):
    await state.update_data(selected_levels=[])
    await callback.message.edit_text("Шаг 1/3 — выберите уровни (сброшено):", reply_markup=levels_keyboard([]))
    await callback.answer()

# Back handlers
@dp.callback_query(lambda c: c.data and c.data.startswith("back:"))
async def cb_back(callback: CallbackQuery, state: FSMContext):
    _, where = callback.data.split(":", 1)
    if where == "levels":
        # from levels keyboard "back" -> main menu
        await state.clear()
        await callback.message.answer("Вы вернулись в главное меню.", reply_markup=simple_menu_keyboard())
    elif where == "audience":
        await state.set_state(OnboardingStates.levels)
        data = await state.get_data()
        await callback.message.answer("Вернулись к выбору уровней:", reply_markup=levels_keyboard(data.get("selected_levels", [])))
    elif where == "textbook":
        await state.set_state(OnboardingStates.audience)
        await callback.message.answer("Вернулись к выбору аудитории:", reply_markup=audience_keyboard())
    elif where == "to_menu":
        await state.clear()
        await callback.message.answer("Вы вернулись в главное меню.", reply_markup=simple_menu_keyboard())
    await callback.answer()

# Audience selection
@dp.callback_query(lambda c: c.data and c.data.startswith("aud:"))
async def cb_audience(callback: CallbackQuery, state: FSMContext):
    aud_map = {
        "aud:school_1_4": "1–4 класс",
        "aud:school_5_7": "5–7 класс",
        "aud:school_8_11": "8–11 класс",
        "aud:university": "университет",
        "aud:work": "работа",
    }
    audience_value = aud_map.get(callback.data, "прочее")
    await state.update_data(audience=audience_value)
    await state.set_state(OnboardingStates.textbook)
    await callback.message.edit_text(f"Шаг 3/3 — вы выбрали: {audience_value}\nВыберите учебник (если есть):", reply_markup=textbook_keyboard())
    await callback.answer()

# Textbook selection -> search and present results
@dp.callback_query(lambda c: c.data and c.data.startswith("tb:"))
async def cb_textbook(callback: CallbackQuery, state: FSMContext):
    _, textbook_choice = callback.data.split(":", 1)
    await state.update_data(textbook=textbook_choice)

    data = await state.get_data()
    levels = data.get("selected_levels", [])
    audience = data.get("audience")
    textbook = textbook_choice

    await callback.message.edit_text("Ищу материалы по вашим фильтрам...")
    lessons = await find_lessons_by_filters(levels=levels, audience_keyword=audience, textbook_keyword=textbook)

    if lessons:
        # показываем первый материал и кнопку для просмотра всех
        lp = lessons[0]
        caption = f"Найдено: {lp.lesson.name}\nУровень: {lp.level}\nОписание: {lp.meta_description or '—'}"
        # Попытка отправить PDF корректно
        try:
            if lp.pdf_file and getattr(lp.pdf_file, "name", None):
                # используем путь на диске
                path = getattr(lp.pdf_file, "path", None)
                if path and os.path.exists(path):
                    await bot.send_document(chat_id=callback.message.chat.id, document=InputFile(path), caption=caption, reply_markup=result_keyboard(str(lp.id), pdf_url=None))
                else:
                    # fallback на URL (MEDIA_URL) если доступен
                    url = getattr(lp.pdf_file, "url", None)
                    if url:
                        await bot.send_document(chat_id=callback.message.chat.id, document=url, caption=caption, reply_markup=result_keyboard(str(lp.id), pdf_url=url))
                    else:
                        # нет файла на диске и нет публичного url -> отправляем ссылку на сайт
                        await callback.message.answer(f"{caption}\n\nPDF пока недоступен. Откройте на сайте: https://linguaglow.ru/lesson/{lp.link_name}", reply_markup=result_keyboard(str(lp.id)))
            else:
                # нет pdf в записи — отправляем ссылку на сайт
                await callback.message.answer(f"{caption}\n\nPDF пока недоступен. Откройте на сайте: https://linguaglow.ru/lesson/{lp.link_name}", reply_markup=result_keyboard(str(lp.id)))
            await callback.answer()
            # При желании — обновить метрики (например, pdf_downloaded) — вынесено из try, т.к. прямое скачивание может не быть совершено
        except Exception as e:
            print(f"[WARN] send PDF error: {e}")
            await callback.message.answer(f"{caption}\n\n(Не удалось отправить PDF прямо в чат.)\nОткрыть на сайте: https://linguaglow.ru/lesson/{lp.link_name}", reply_markup=result_keyboard(str(lp.id)))
            await callback.answer()
    else:
        # если ничего не найдено — предлагаем посмотреть любые материалы
        await callback.message.answer(
            "Мы пока не нашли материалов по заданным фильтрам. "
            "Можем показать другие доступные уроки или вы можете создать свой урок.",
            reply_markup=result_keyboard(None)
        )
        await callback.answer()

# ---------------------------
# Result actions: more_like_this, view_all, notify
# ---------------------------
@dp.callback_query(lambda c: c.data and c.data.startswith("action:more_like_this"))
async def cb_more_like(callback: CallbackQuery, state: FSMContext):
    # format: action:more_like_this:<lesson_public_id>
    parts = callback.data.split(":")
    lesson_public_id = parts[-1] if len(parts) >= 3 else None
    data = await state.get_data()
    lessons = await find_lessons_by_filters(levels=data.get("selected_levels", []), audience_keyword=data.get("audience"), textbook_keyword=data.get("textbook"))
    if not lessons:
        await callback.message.answer("Похожих материалов не найдено.", reply_markup=result_keyboard(None))
        await callback.answer()
        return
    # Отправляем краткий список (6 шт)
    text_lines = [format_lesson_short(lp) for lp in lessons[:6]]
    await callback.message.answer("Похожие уроки:\n\n" + "\n".join(text_lines), reply_markup=result_keyboard(None))
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data == "action:view_all")
async def cb_view_all(callback: CallbackQuery, state: FSMContext):
    lessons = await list_all_public_lessons(limit=50)
    if not lessons:
        await callback.message.answer("Материалов с PDF пока нет.")
        await callback.answer()
        return
    text_lines = [format_lesson_short(lp) for lp in lessons[:20]]
    text = "Все доступные материалы (первые 20):\n\n" + "\n".join(text_lines)
    await callback.message.answer(text, reply_markup=simple_menu_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data == "action:notify_when_ready")
async def cb_notify(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    metrics_id = data.get("metrics_id")
    if metrics_id:
        try:
            metrics = await sync_to_async(lambda: TelegramMetrics.objects.get(id=metrics_id))()
            if hasattr(metrics, "notify_on_new_material"):
                await save_metrics_update(metrics, notify_on_new_material=True)
        except Exception:
            pass
    await callback.message.answer("Окей! Мы пришлем уведомление в этот чат, когда появятся материалы по вашим фильтрам.")
    await callback.answer()

# ---------------------------
# Polling loop with reconnect
# ---------------------------
async def safe_polling():
    while True:
        try:
            me = await bot.get_me()
            print(f"[INFO] Bot: {me.username} (id={me.id})")
            await dp.start_polling(bot)
        except TelegramNetworkError as e:
            print(f"[WARNING] TelegramNetworkError: {e}. Reconnect in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[ERROR] Unexpected polling error: {e}")
            await asyncio.sleep(5)

# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except Exception:
        pass

    try:
        asyncio.run(safe_polling())
    finally:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(session.close())
        except Exception:
            pass
