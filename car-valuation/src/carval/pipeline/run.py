"""Сборка конвейера: фото → предварительный отчёт."""

from __future__ import annotations

from ..catalog import Catalog
from ..checklist import missing_required, photos_by_zone
from ..llm import LLM
from ..models import Car, Photo, Report
from ..pricing import estimate_price
from ..settings import Settings
from ..storage import Storage
from .decision import needs_manual_review
from .inspector import inspect_all
from .reviewer import review
from .shot_controller import check_quality


async def analyze(
    car: Car,
    photos: list[Photo],
    *,
    catalog: Catalog,
    llm: LLM,
    storage: Storage,
    settings: Settings,
) -> Report:
    report = Report(car=car, photos=photos)
    report.missing_angles = [a.id for a in missing_required(catalog.angles, photos)]

    data = {p.angle_id: await storage.load_photo(p.storage_key) for p in photos}

    # 1. Контролёр съёмки
    report.photo_issues = await check_quality(
        list(data.items()), catalog=catalog, llm=llm, settings=settings
    )
    bad = {i.angle_id for i in report.photo_issues}

    # 2. Дефектоскопы по зонам (непригодные фото не отправляем)
    zone_photos = {
        zone: [(p.angle_id, data[p.angle_id]) for p in ps if p.angle_id not in bad]
        for zone, ps in photos_by_zone(catalog.angles, photos).items()
    }
    report.defects, report.not_assessable = await inspect_all(
        zone_photos, car=car, catalog=catalog, llm=llm, settings=settings
    )

    # 3–5. Цена, ревью, пометка
    await refresh(report, catalog=catalog, llm=llm, settings=settings)
    return report


def reprice(report: Report, *, catalog: Catalog, settings: Settings) -> Report:
    """Быстрый пересчёт без ИИ: после того как оценщик подтвердил или отклонил дефект."""
    report.estimate = estimate_price(
        report.car, report.active_defects, catalog.comparables, catalog.repair_prices, settings.currency
    )
    report.needs_manual_review = needs_manual_review(report)
    return report


async def refresh(report: Report, *, catalog: Catalog, llm: LLM, settings: Settings) -> Report:
    """Полный пересчёт: цена + ревьюер (платный запрос) + пометка."""
    reprice(report, catalog=catalog, settings=settings)
    report.review = await review(report, llm=llm, settings=settings)
    report.needs_manual_review = needs_manual_review(report)
    return report
