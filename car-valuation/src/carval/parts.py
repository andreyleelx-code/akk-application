"""Варианты ремонта: своя база, подрядчики и (если там пусто) интернет.

Для каждого дефекта собираем варианты из config/suppliers.csv:
ремонт, замена оригиналом, аналогом или б/у — с ценой детали, работы и сроком.
Если ни у себя, ни у подрядчиков варианта нет, pipeline/parts_scout.py ищет
цены на открытых сайтах. Выбранный вариант идёт в вычет на ремонт.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from .models import Car, Defect, RepairOption, Report, Severity
from .settings import Settings

KIND_RU = {"repair": "ремонт", "oem": "оригинал", "analog": "аналог", "used": "б/у"}
SOURCE_RU = {"own": "своя база", "contractor": "подрядчик", "web": "интернет"}


@dataclass(frozen=True)
class SupplierRow:
    supplier: str
    source: str
    make: str
    defect_code: str
    severity: str
    kind: str
    parts: int
    labor: int
    days: int | None
    contact: str
    note: str

    def matches(self, car: Car, d: Defect) -> bool:
        return (
            self.defect_code == d.code
            and self.severity in ("*", d.severity.value)
            and self.make in ("*", car.make.lower())
        )


def load_suppliers(settings: Settings) -> list[SupplierRow]:
    path = settings.config_file("suppliers.csv")
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [
            SupplierRow(
                supplier=r["supplier"], source=r["source"], make=r["make"].strip().lower() or "*",
                defect_code=r["defect_code"], severity=r["severity"] or "*", kind=r["kind"],
                parts=int(r["parts_kzt"] or 0), labor=int(r["labor_kzt"] or 0),
                days=int(r["days"]) if r["days"] else None, contact=r["contact"], note=r["note"],
            )
            for r in csv.DictReader(f)
        ]


def base_options(car: Car, d: Defect, suppliers: list[SupplierRow]) -> list[RepairOption]:
    return [
        RepairOption(kind=s.kind, supplier=s.supplier, source=s.source, parts_cost=s.parts,
                     labor_cost=s.labor, days=s.days, note=s.note)
        for s in suppliers if s.matches(car, d)
    ]


def choose_option(options: list[RepairOption]) -> int | None:
    """Какой вариант брать в расчёт по умолчанию.

    Сейчас: самый дешёвый из своей базы и подрядчиков; при равной цене — быстрее.
    Цены из интернета берём, только если в базе ничего нет: их ещё надо проверить.
    Оценщик может выбрать другой вариант вручную.
    """
    if not options:
        return None
    trusted = [i for i, o in enumerate(options) if o.source != "web"]
    pool = trusted or list(range(len(options)))
    return min(pool, key=lambda i: (options[i].total, options[i].days or 99))


def needs_parts(d: Defect, repair_prices: dict[tuple[str, Severity], int]) -> bool:
    """Дефект, который реально ремонтируют (не «информационный» с ценой 0)."""
    return repair_prices.get((d.code, d.severity), 0) > 0


def attach_options(report: Report, suppliers: list[SupplierRow]) -> list[Defect]:
    """Подставляет варианты из базы. Возвращает дефекты, для которых в базе пусто."""
    uncovered = []
    for d in report.defects:
        d.options = base_options(report.car, d, suppliers)
        d.chosen = choose_option(d.options)
        if not d.options:
            uncovered.append(d)
    return uncovered
