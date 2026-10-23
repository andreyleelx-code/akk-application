"""Когда ставить пометку «проверить вручную».

Это бизнес-правило, а не техника: оно определяет, сколько машин старший
оценщик будет смотреть сам, а сколько утвердит по отчёту.
"""

from __future__ import annotations

from ..models import DefectStatus, Report, Severity

LOW_CONFIDENCE = 0.6
REVIEW_CONFIDENCE = 0.7


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

    Правило по умолчанию (то же показано в презентации). Меняйте под регламент:
    чем строже, тем меньше пропусков, но больше ручной работы старшего.
    """
    if report.missing_angles or report.photo_issues:
        return True  # отчёт построен не по всем фото
    active = report.active_defects
    if any(d.severity == Severity.severe for d in active):
        return True  # серьёзное повреждение или признак ДТП
    if any(d.status == DefectStatus.pending and d.confidence < LOW_CONFIDENCE for d in active):
        return True  # ИИ сомневается, а человек ещё не посмотрел
    if report.review and report.review.overall_confidence < REVIEW_CONFIDENCE:
        return True
    st = report.settlement
    if st and (st.due > 0 or st.insurance_case):
        return True  # прокат: удержание больше депозита или страховой случай
    if report.kind == "buyback" and report.estimate is None:
        return True  # нет аналогов — цену назначает человек
    return False
