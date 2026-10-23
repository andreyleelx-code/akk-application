"""Сценарий оценщика:

1. /new — карточка: VIN или госномер, марка и модель, год, пробег
2. Бот ведёт по чек-листу и просит каждый ракурс
3. Фото → предварительный отчёт за 1–3 минуты
4. Оценщик подтверждает/отклоняет дефекты, добавляет замеры
5. Старший оценщик утверждает итоговую цену
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InputMediaPhoto, Message, ReplyKeyboardRemove,
)

from ..annotate import annotate, defects_by_photo

from ..catalog import Catalog
from ..checklist import next_angle
from ..llm import LLM, LLMError
from ..models import Car, DefectStatus, Photo, Report
from ..pipeline.run import analyze, refresh, reprice
from ..report import render
from ..settings import Settings
from ..storage import Storage
from .keyboards import DONE, SKIP, approve_kb, report_kb, shooting_kb
from .states import NewCase, ReportEdit

log = logging.getLogger(__name__)
router = Router()

HELP = (
    "Я помогаю оценщику: веду по чек-листу съёмки, ищу видимые дефекты "
    "и считаю диапазон цены.\n\n"
    "/new — новая оценка\n/cancel — отменить\n\n"
    "Я второй взгляд, а не замена оценщику: финальное решение всегда за человеком."
)


async def safe_edit(cb: CallbackQuery, text: str, **kwargs) -> None:
    """Повторное нажатие той же кнопки не меняет текст — Telegram отвечает ошибкой, её глушим."""
    try:
        await cb.message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise


# ---------- Общие команды ----------


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())


# ---------- 1. Карточка автомобиля ----------


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewCase.vin)
    await message.answer("VIN или госномер:", reply_markup=ReplyKeyboardRemove())


@router.message(NewCase.vin, F.text)
async def got_vin(message: Message, state: FSMContext) -> None:
    await state.update_data(vin=message.text.strip().upper())
    await state.set_state(NewCase.make_model)
    await message.answer("Марка и модель (например: Toyota Camry):")


@router.message(NewCase.make_model, F.text)
async def got_make_model(message: Message, state: FSMContext) -> None:
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Нужны марка и модель через пробел, например: Hyundai Tucson")
        return
    await state.update_data(make=parts[0], model=parts[1])
    await state.set_state(NewCase.year)
    await message.answer("Год выпуска:")


@router.message(NewCase.year, F.text)
async def got_year(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or not 1980 <= int(text) <= date.today().year + 1:
        await message.answer("Год числом, например 2018")
        return
    await state.update_data(year=int(text))
    await state.set_state(NewCase.mileage)
    await message.answer("Пробег, км:")


@router.message(NewCase.mileage, F.text)
async def got_mileage(message: Message, state: FSMContext, catalog: Catalog) -> None:
    text = message.text.replace(" ", "").strip()
    if not text.isdigit():
        await message.answer("Пробег числом, например 120000")
        return
    await state.update_data(mileage=int(text), case_id=uuid4().hex[:12], photos=[], skipped=[])
    await state.set_state(NewCase.photos)
    await message.answer(
        "Начинаем съёмку. Снимайте при хорошем свете, без бликов, вся деталь в кадре. "
        "Можно отправлять фото как файл: так качество лучше."
    )
    await ask_next_angle(message, state, catalog)


# ---------- 2. Съёмка по чек-листу ----------


async def ask_next_angle(message: Message, state: FSMContext, catalog: Catalog) -> bool:
    """Просит следующий ракурс. False — чек-лист пройден."""
    data = await state.get_data()
    photos = [Photo(**p) for p in data["photos"]]
    angle = next_angle(catalog.angles, photos, set(data["skipped"]))
    if angle is None:
        return False
    await state.update_data(current=angle.id)
    total = len(catalog.angles)
    mark = "" if angle.required else " (необязательно)"
    await message.answer(
        f"📷 {len(photos) + len(data['skipped']) + 1}/{total}: {angle.title}{mark}",
        reply_markup=shooting_kb(optional=not angle.required),
    )
    return True


@router.message(NewCase.photos, F.photo | F.document)
async def got_photo(
    message: Message, state: FSMContext, bot: Bot,
    catalog: Catalog, repo: Storage, llm: LLM, settings: Settings,
) -> None:
    if message.document and not (message.document.mime_type or "").startswith("image/"):
        await message.answer("Это не изображение. Пришлите фото.")
        return
    data = await state.get_data()
    file = message.photo[-1] if message.photo else message.document
    buf = await bot.download(file)
    key = await repo.save_photo(data["case_id"], data["current"], buf.read())

    photos = [p for p in data["photos"] if p["angle_id"] != data["current"]]
    photos.append(Photo(angle_id=data["current"], storage_key=key).model_dump())
    await state.update_data(photos=photos)

    if not await ask_next_angle(message, state, catalog):
        await finish_shooting(message, state, catalog, repo, llm, settings)


@router.message(NewCase.photos, F.text == SKIP)
async def skip_angle(message: Message, state: FSMContext, catalog: Catalog,
                     repo: Storage, llm: LLM, settings: Settings) -> None:
    data = await state.get_data()
    angle = catalog.angle(data["current"])
    if angle and angle.required:
        await message.answer("Этот ракурс обязательный. Если снять нельзя, нажмите «Готово».")
        return
    await state.update_data(skipped=[*data["skipped"], data["current"]])
    if not await ask_next_angle(message, state, catalog):
        await finish_shooting(message, state, catalog, repo, llm, settings)


@router.message(NewCase.photos, F.text == DONE)
async def done_shooting(message: Message, state: FSMContext, catalog: Catalog,
                        repo: Storage, llm: LLM, settings: Settings) -> None:
    await finish_shooting(message, state, catalog, repo, llm, settings)


@router.message(NewCase.photos)
async def shooting_hint(message: Message) -> None:
    await message.answer(f"Пришлите фото этого ракурса или нажмите «{DONE}», чтобы закончить съёмку.")


# ---------- 3. Анализ ----------


async def finish_shooting(message: Message, state: FSMContext, catalog: Catalog,
                          repo: Storage, llm: LLM, settings: Settings) -> None:
    data = await state.get_data()
    await state.clear()
    photos = [Photo(**p) for p in data["photos"]]
    if not photos:
        await message.answer("Нет ни одного фото. Начните заново: /new", reply_markup=ReplyKeyboardRemove())
        return

    car = Car(vin_or_plate=data["vin"], make=data["make"], model=data["model"],
              year=data["year"], mileage_km=data["mileage"])
    await message.answer("⏳ Анализирую фото, это займёт 1–3 минуты…", reply_markup=ReplyKeyboardRemove())
    try:
        report = await analyze(car, photos, catalog=catalog, llm=llm, storage=repo, settings=settings)
    except LLMError as e:
        log.exception("analyze failed")
        await message.answer(f"Не удалось построить отчёт: {e}. Фото сохранены, попробуйте позже.")
        return
    await repo.save_report(report)
    await send_annotated(message, report, repo)
    await message.answer(render(report, catalog), reply_markup=report_kb(report))


async def send_annotated(message: Message, report: Report, repo: Storage) -> None:
    """Фото с рамками дефектов: номер на фото = номер в отчёте."""
    keys = {p.angle_id: p.storage_key for p in report.photos}
    media = []
    for angle_id, items in defects_by_photo(report).items():
        if angle_id not in keys:
            continue
        marked = annotate(await repo.load_photo(keys[angle_id]), items)
        caption = ", ".join(f"№{n}" for n, _ in items) + f" — {angle_id}"
        media.append(InputMediaPhoto(media=BufferedInputFile(marked, f"{angle_id}.jpg"), caption=caption))
    for i in range(0, len(media), 10):  # Telegram: до 10 фото в альбоме
        try:
            await message.answer_media_group(media[i : i + 10])
        except TelegramAPIError:
            log.exception("cannot send annotated photos")


# ---------- 4. Правки оценщика ----------


@router.callback_query(F.data.startswith("d:"))
async def on_defect(cb: CallbackQuery, catalog: Catalog, repo: Storage, settings: Settings) -> None:
    _, report_id, defect_id, action = cb.data.split(":")
    report = await repo.get_report(report_id)
    if report is None:
        await cb.answer("Отчёт не найден", show_alert=True)
        return
    for d in report.defects:
        if d.id == defect_id:
            d.status = DefectStatus.confirmed if action == "c" else DefectStatus.rejected
    reprice(report, catalog=catalog, settings=settings)
    await repo.save_report(report)
    await safe_edit(cb, render(report, catalog), reply_markup=report_kb(report))
    await cb.answer()


@router.callback_query(F.data.startswith("note:"))
async def on_note(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ReportEdit.note)
    await state.update_data(report_id=cb.data.split(":")[1])
    await cb.message.answer(
        "Напишите, что ИИ не мог увидеть: замеры толщиномера, ошибки OBD, проверку по VIN.\n"
        "Например: «Левая передняя дверь 280 мкм — перекрас»"
    )
    await cb.answer()


@router.message(ReportEdit.note, F.text)
async def got_note(message: Message, state: FSMContext, catalog: Catalog,
                   repo: Storage, settings: Settings) -> None:
    report_id = (await state.get_data())["report_id"]
    await state.clear()
    report = await repo.get_report(report_id)
    if report is None:
        await message.answer("Отчёт не найден")
        return
    report.manual_notes.append(message.text.strip())
    reprice(report, catalog=catalog, settings=settings)
    await repo.save_report(report)
    await message.answer(render(report, catalog), reply_markup=report_kb(report))


@router.callback_query(F.data.startswith("rev:"))
async def on_review(cb: CallbackQuery, catalog: Catalog, repo: Storage,
                    llm: LLM, settings: Settings) -> None:
    report = await repo.get_report(cb.data.split(":")[1])
    if report is None:
        await cb.answer("Отчёт не найден", show_alert=True)
        return
    await cb.answer("Перепроверяю…")
    try:
        await refresh(report, catalog=catalog, llm=llm, settings=settings)
    except LLMError as e:
        await cb.message.answer(f"Не удалось перепроверить: {e}")
        return
    await repo.save_report(report)
    await safe_edit(cb, render(report, catalog), reply_markup=report_kb(report))


# ---------- 5. Утверждение старшим ----------


@router.callback_query(F.data.startswith("send:"))
async def on_send(cb: CallbackQuery, bot: Bot, catalog: Catalog,
                  repo: Storage, settings: Settings) -> None:
    report = await repo.get_report(cb.data.split(":")[1])
    if report is None:
        await cb.answer("Отчёт не найден", show_alert=True)
        return
    if not settings.senior_ids:
        await cb.answer("Не настроены старшие оценщики (SENIOR_APPRAISER_IDS)", show_alert=True)
        return
    pending = [d for d in report.defects if d.status == DefectStatus.pending]
    if pending:
        await cb.answer(f"Сначала подтвердите или отклоните все дефекты (осталось {len(pending)})",
                        show_alert=True)
        return
    delivered = 0
    for senior in settings.senior_ids:
        try:
            await bot.send_message(senior, render(report, catalog), reply_markup=approve_kb(report))
            delivered += 1
        except TelegramAPIError:
            log.warning("cannot message senior %s: they must /start the bot first", senior)
    if delivered:
        await cb.answer("Отправлено старшему оценщику")
    else:
        await cb.answer("Старший оценщик ещё не запускал бота — попросите его нажать /start",
                        show_alert=True)


@router.callback_query(F.data.startswith("ok:"))
async def on_approve(cb: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if cb.from_user.id not in settings.senior_ids:
        await cb.answer("Утверждать цену может только старший оценщик", show_alert=True)
        return
    await state.set_state(ReportEdit.approve_price)
    await state.update_data(report_id=cb.data.split(":")[1])
    await cb.message.answer("Итоговая цена выкупа, ₸:")
    await cb.answer()


@router.message(ReportEdit.approve_price, F.text)
async def got_price(message: Message, state: FSMContext, catalog: Catalog,
                    repo: Storage, settings: Settings) -> None:
    text = message.text.replace(" ", "").strip()
    if not text.isdigit():
        await message.answer("Цена числом, например 11500000")
        return
    report_id = (await state.get_data())["report_id"]
    await state.clear()
    report = await repo.get_report(report_id)
    if report is None:
        await message.answer("Отчёт не найден")
        return
    report.approved_price = int(text)
    report.approved_by = message.from_user.id
    await repo.save_report(report)
    await message.answer(render(report, catalog))
