"""Шаг 4. Ревьюер: перепроверяет находки и расчёт, ищет противоречия."""

from __future__ import annotations

import json

from ..llm import LLM, text_block
from ..models import Report, Review
from ..settings import Settings
from . import load_prompt


async def review(report: Report, *, llm: LLM, settings: Settings) -> Review:
    payload = {
        "car": report.car.model_dump(),
        "defects": [d.model_dump(mode="json") for d in report.active_defects],
        "not_assessable": report.not_assessable,
        "estimate": report.estimate.model_dump() if report.estimate else None,
        "manual_notes": report.manual_notes,
    }
    return await llm.parse(
        model=settings.model_main,
        system=load_prompt(settings, "reviewer"),
        content=[text_block(json.dumps(payload, ensure_ascii=False, indent=2))],
        schema=Review,
        effort="medium",
        max_tokens=8000,
    )
