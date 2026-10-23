"""Прокат: сравнение осмотра при возврате с осмотром при выдаче и расчёт с клиентом.

Новое повреждение — то, чего не было в акте выдачи. Совпадение ищем по зоне,
типу дефекта и месту на фото (пересечение рамок). Всё, что было при выдаче,
клиенту не выставляется — именно этим акт выдачи с фото закрывает споры.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .catalog import Catalog
from .models import Defect, DefectStatus, Report, Settlement
from .pricing import defect_cost
from .settings import Settings


@dataclass(frozen=True)
class RentalTerms:
    km_per_day: int
    extra_km_kzt: int
    fuel_kzt_per_l: int
    deposit_default: int
    wash_kzt: dict[str, int]
    insurance_threshold_kzt: int


def load_terms(settings: Settings) -> RentalTerms:
    data = yaml.safe_load((settings.config_dir / "rental.yaml").read_text("utf-8"))
    return RentalTerms(**data)


def _iou(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def was_there(d: Defect, before: list[Defect], min_iou: float = 0.15) -> bool:
    """Был ли такой дефект при выдаче."""
    for old in before:
        if old.zone != d.zone or old.code != d.code:
            continue
        if old.angle_id == d.angle_id and (not d.box or not old.box or _iou(d.box, old.box) >= min_iou):
            return True
    return False


def settle(ret: Report, handover: Report, catalog: Catalog, terms: RentalTerms) -> Settlement:
    before = handover.active_defects
    current = [d for d in ret.defects if d.status != DefectStatus.rejected]
    new = [d for d in current if not was_there(d, before)]
    new_ids = {d.id for d in new}
    known = [d for d in current if d.id not in new_ids]

    info, out = ret.rental, handover.rental
    deposit = (out.deposit if out and out.deposit else terms.deposit_default)
    days = out.days if out else 1
    km_out = out.km_out if out else None
    km_in = info.km_in if info else None
    body = (out.body if out else "sedan")

    repair = sum(defect_cost(d, catalog.repair_prices) for d in new)
    extra_km = max(0, (km_in - km_out) - terms.km_per_day * days) if km_in and km_out else 0
    wash = terms.wash_kzt.get(body, 0) if info and info.dirty else 0
    fuel = round((info.fuel_missing_l if info else 0) * terms.fuel_kzt_per_l)
    total = repair + wash + extra_km * terms.extra_km_kzt + fuel
    return Settlement(
        new_defect_ids=[d.id for d in new], known_defect_ids=[d.id for d in known],
        repair=repair, wash=wash, extra_km=extra_km, extra_km_cost=extra_km * terms.extra_km_kzt,
        fuel=fuel, total=total, deposit=deposit,
        refund=max(deposit - total, 0), due=max(total - deposit, 0),
        insurance_case=repair >= terms.insurance_threshold_kzt,
    )
