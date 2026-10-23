"""Отчёт для Telegram (HTML-разметка)."""

from __future__ import annotations

from html import escape

from .catalog import Catalog
from .models import DefectStatus, Report, Severity
from .parts import KIND_RU, SOURCE_RU

SEVERITY_RU = {Severity.minor: "лёгкий", Severity.moderate: "средний", Severity.severe: "серьёзный"}
STATUS_MARK = {
    DefectStatus.pending: "❔",
    DefectStatus.confirmed: "✅",
    DefectStatus.rejected: "❌",
    DefectStatus.manual: "✍️",
}
TELEGRAM_LIMIT = 4000


def money(value: int, currency: str = "KZT") -> str:
    sign = "₸" if currency == "KZT" else currency
    return f"{value:,}".replace(",", " ") + f" {sign}"


def render(report: Report, catalog: Catalog) -> str:
    car = report.car
    lines = [
        f"<b>Оценка {escape(car.make)} {escape(car.model)}, {car.year}</b>",
        f"{escape(car.vin_or_plate)} · пробег {money(car.mileage_km, 'км')}",
        "",
    ]

    if report.needs_manual_review:
        lines.append("⚠️ <b>Проверить вручную</b>")
    if report.missing_angles:
        lines.append(f"Не сняты: {escape(', '.join(report.missing_angles))}")
    for issue in report.photo_issues:
        lines.append(f"Переснять [{escape(issue.angle_id)}]: {escape(issue.problem)}")

    est = report.estimate
    lines.append("")
    if est:
        lines += [
            f"<b>Предложение: {money(est.offer_low, est.currency)} – {money(est.offer_high, est.currency)}</b>",
            f"Рынок: {money(est.market_low, est.currency)} – {money(est.market_high, est.currency)}"
            f" (медиана {money(est.market_median, est.currency)}, аналогов: {est.comparables_count})",
            f"Вычет на ремонт: {money(est.repair_cost, est.currency)}",
        ]
    else:
        lines.append("<b>Аналогов нет — цену вносит оценщик</b>")
    if report.review:
        lines.append(f"Уверенность: {round(report.review.overall_confidence * 100)}%")

    lines += ["", f"<b>Дефекты ({len(report.active_defects)}):</b>"]
    for i, d in enumerate(report.defects, 1):
        name = catalog.defect_name(d.zone, d.code)
        lines.append(
            f"{STATUS_MARK[d.status]} {i}. {escape(name)}, {SEVERITY_RU[d.severity]} — "
            f"{escape(d.location)} [{escape(d.angle_id)}], {round(d.confidence * 100)}%"
        )
        opt = d.repair_option
        if opt and d.status != DefectStatus.rejected:
            days = f", {opt.days} дн." if opt.days else ""
            lines.append(
                f"    ↳ {KIND_RU[opt.kind]}: {escape(opt.supplier)} ({SOURCE_RU[opt.source]}) — "
                f"{money(opt.total)}{days}" + (f", вариантов: {len(d.options)}" if len(d.options) > 1 else "")
            )

    if report.not_assessable:
        lines += ["", "<b>Проверить инструментом:</b>"]
        lines += [f"• {escape(n)}" for n in report.not_assessable]
    if report.review and report.review.findings:
        lines += ["", f"<b>Ревьюер:</b> {escape(report.review.summary)}"]
        lines += [f"• {escape(f.note)}" for f in report.review.findings]
    if report.manual_notes:
        lines += ["", "<b>Замеры оценщика:</b>"]
        lines += [f"• {escape(n)}" for n in report.manual_notes]
    if report.approved_price is not None:
        lines += ["", f"🟢 <b>Утверждено: {money(report.approved_price)}</b>"]

    # Режем по целым строкам, чтобы не разорвать HTML-тег
    out, size = [], 0
    for line in lines:
        if size + len(line) + 1 > TELEGRAM_LIMIT:
            out.append("…\n(полный отчёт — в веб-панели)")
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)
