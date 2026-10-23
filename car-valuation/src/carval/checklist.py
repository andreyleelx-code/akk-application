"""Контроль полноты съёмки: какие обязательные ракурсы ещё не сняты.

Это детерминированная проверка без ИИ — самая надёжная часть автоматизации.
Качество фото (размыто/темно) проверяет отдельно pipeline.shot_controller.
"""

from __future__ import annotations

from .models import AngleSpec, Photo


def missing_required(angles: list[AngleSpec], photos: list[Photo]) -> list[AngleSpec]:
    taken = {p.angle_id for p in photos}
    return [a for a in angles if a.required and a.id not in taken]


def next_angle(angles: list[AngleSpec], photos: list[Photo], skipped: set[str]) -> AngleSpec | None:
    """Следующий ракурс для бота: первый не снятый и не пропущенный."""
    taken = {p.angle_id for p in photos}
    for a in angles:
        if a.id not in taken and a.id not in skipped:
            return a
    return None


def photos_by_zone(angles: list[AngleSpec], photos: list[Photo]) -> dict[str, list[Photo]]:
    zone_of = {a.id: a.zone for a in angles}
    grouped: dict[str, list[Photo]] = {}
    for p in photos:
        grouped.setdefault(zone_of.get(p.angle_id, "body"), []).append(p)
    return grouped
