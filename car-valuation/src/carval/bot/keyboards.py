from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..models import Report

SKIP = "Пропустить"
DONE = "Готово"


def shooting_kb(optional: bool) -> ReplyKeyboardMarkup:
    row = [KeyboardButton(text=DONE)]
    if optional:
        row.insert(0, KeyboardButton(text=SKIP))
    return ReplyKeyboardMarkup(keyboard=[row], resize_keyboard=True)


def report_kb(report: Report) -> InlineKeyboardMarkup:
    """Кнопки ✅/❌ на каждый дефект + действия с отчётом."""
    kb = InlineKeyboardBuilder()
    for i, d in enumerate(report.defects, 1):
        kb.button(text=f"✅ {i}", callback_data=f"d:{report.id}:{d.id}:c")
        kb.button(text=f"❌ {i}", callback_data=f"d:{report.id}:{d.id}:r")
    kb.adjust(4)  # два дефекта в строке

    actions = InlineKeyboardBuilder()
    actions.button(text="✍️ Замер / OBD", callback_data=f"note:{report.id}")
    actions.button(text="🔄 Перепроверить", callback_data=f"rev:{report.id}")
    actions.button(text="📤 Старшему", callback_data=f"send:{report.id}")
    actions.adjust(3)
    kb.attach(actions)
    return kb.as_markup()


def approve_kb(report: Report) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Утвердить цену", callback_data=f"ok:{report.id}")
    return kb.as_markup()
