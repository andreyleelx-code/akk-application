"""Поиск запчастей и работ в интернете для дефектов, которых нет в базе поставщиков.

Шаг 1: Claude с веб-поиском находит предложения на казахстанских сайтах.
Шаг 2: быстрая модель раскладывает найденное в таблицу (ScoutResult).
Найденные цены помечаются источником «интернет»: их проверяет человек.
"""

from __future__ import annotations

from ..llm import LLM, text_block
from ..models import Car, Defect, RepairOption, ScoutResult
from ..parts import choose_option
from ..settings import Settings
from . import load_prompt
from .inspector import _car_line


async def scout(
    defects: list[Defect], *, car: Car, defect_names: dict[str, str], llm: LLM, settings: Settings
) -> None:
    """Дописывает найденные варианты в defect.options и выбирает вариант по умолчанию."""
    if not defects:
        return
    lines = "\n".join(
        f"- {d.id} — {defect_names.get(d.id, d.code)} — {d.location} — {d.severity.value}" for d in defects
    )
    prompt = load_prompt(settings, "parts_scout", city=settings.city, car=_car_line(car), defects=lines)
    found_text, urls = await llm.search(
        model=settings.model_main, system="Отвечай по-русски, коротко, с адресами страниц.", prompt=prompt
    )
    if not found_text.strip():
        return

    result = await llm.parse(
        model=settings.model_fast,
        system="Разложи найденные предложения в таблицу. Ничего не добавляй от себя. "
               "Берите только предложения с адресом страницы.",
        content=[text_block(f"id дефектов: {', '.join(d.id for d in defects)}\n\n{found_text}")],
        schema=ScoutResult,
        effort="low",
        max_tokens=8000,
    )
    seen = set(urls)
    by_id = {d.id: d for d in defects}
    for offer in result.offers:
        d = by_id.get(offer.defect_id)
        # адрес должен быть из настоящей выдачи поиска, иначе предложение не берём
        if d is None or (seen and offer.url not in seen):
            continue
        d.options.append(RepairOption(
            kind=offer.kind, supplier=offer.supplier, source="web", url=offer.url,
            parts_cost=offer.parts_kzt, labor_cost=offer.labor_kzt,
            note=offer.note + ("" if offer.labor_kzt else " · работа не найдена, уточнить"),
        ))
    for d in defects:
        d.chosen = choose_option(d.options)
