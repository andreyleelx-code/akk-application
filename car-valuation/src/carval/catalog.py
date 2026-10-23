"""Загрузка справочников из config/: чек-лист, дефекты, прайс ремонта, аналоги."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import AngleSpec, Severity
from .settings import Settings


@dataclass(frozen=True)
class Comparable:
    make: str
    model: str
    year: int
    mileage_km: int
    price: int


@dataclass(frozen=True)
class Catalog:
    zones: dict[str, str]  # zone_id -> название
    angles: list[AngleSpec]
    defects: dict[str, dict[str, str]]  # zone_id -> {code: название}
    repair_prices: dict[tuple[str, Severity], int]  # (code, severity) -> цена
    comparables: list[Comparable]

    def angle(self, angle_id: str) -> AngleSpec | None:
        return next((a for a in self.angles if a.id == angle_id), None)

    def defect_name(self, zone: str, code: str) -> str:
        return self.defects.get(zone, {}).get(code, code)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_catalog(settings: Settings) -> Catalog:
    checklist = yaml.safe_load(settings.config_file("checklist.yaml").read_text("utf-8"))
    defects = yaml.safe_load(settings.config_file("defects.yaml").read_text("utf-8"))

    prices = {
        (r["defect_code"], Severity(r["severity"])): int(r["cost_kzt"])
        for r in _read_csv(settings.config_file("repair_prices.csv"))
    }
    comparables = [
        Comparable(r["make"], r["model"], int(r["year"]), int(r["mileage_km"]), int(r["price_kzt"]))
        for r in _read_csv(settings.config_file("comparables.csv"))
    ]
    return Catalog(
        zones=checklist["zones"],
        angles=[AngleSpec(**a) for a in checklist["angles"]],
        defects=defects,
        repair_prices=prices,
        comparables=comparables,
    )
