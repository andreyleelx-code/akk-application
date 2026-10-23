"""Шаг 1. Контролёр съёмки: пригодны ли фото (дешёвая быстрая модель)."""

from __future__ import annotations

from ..catalog import Catalog
from ..llm import LLM, image_block, text_block
from ..models import PhotoIssue, ShotQuality
from ..settings import Settings
from . import load_prompt

BATCH = 20  # фото в одном запросе


async def check_quality(
    photos: list[tuple[str, bytes]],  # (angle_id, данные)
    *,
    catalog: Catalog,
    llm: LLM,
    settings: Settings,
) -> list[PhotoIssue]:
    system = load_prompt(settings, "shot_controller")
    issues: list[PhotoIssue] = []
    for i in range(0, len(photos), BATCH):
        content: list[dict] = []
        for angle_id, data in photos[i : i + BATCH]:
            spec = catalog.angle(angle_id)
            content.append(text_block(f"[{angle_id}] {spec.title if spec else angle_id}"))
            content.append(image_block(data))
        content.append(text_block("Проверь пригодность этих фото."))
        result = await llm.parse(
            model=settings.model_fast, system=system, content=content,
            schema=ShotQuality, effort="low", max_tokens=4000,
        )
        issues.extend(result.unusable)
    return issues
