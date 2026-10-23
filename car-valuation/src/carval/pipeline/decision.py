"""Когда ставить пометку «проверить вручную».

Это бизнес-правило, а не техника: оно определяет, сколько машин старший
оценщик будет смотреть сам, а сколько утвердит по отчёту.
"""

from __future__ import annotations

from ..models import Report


def needs_manual_review(report: Report) -> bool:
    """True — отчёт нельзя утверждать без внимательной ручной проверки.

    Что есть в report для решения:
      report.missing_angles        — не снятые обязательные ракурсы
      report.photo_issues          — непригодные фото
      report.active_defects        — дефекты (у каждого .severity, .confidence, .code)
      report.not_assessable        — что ИИ не смог оценить по фото
      report.estimate              — None, если нет аналогов; иначе .comparables_count,
                                     .repair_cost, .market_median
      report.review                — .overall_confidence и .findings от ревьюера
      report.manual_notes          — замеры толщиномера, OBD, VIN от оценщика

    TODO(вы): определите правило. Сейчас стоит самый осторожный вариант:
    каждый отчёт идёт на ручную проверку. Это безопасно на время пилота,
    но после калибровки старший оценщик захочет видеть только спорные случаи.
    """
    return True
