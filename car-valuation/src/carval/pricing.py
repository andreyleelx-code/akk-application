"""Расчёт цены: рынок по аналогам минус ремонт по прайсу заказчика.

Деньги считает код, а не ИИ: формула прозрачна, её можно проверить и объяснить.
"""

from __future__ import annotations

from statistics import median, quantiles

from .catalog import Comparable
from .models import Car, Defect, PriceEstimate, Severity

# Насколько далеко по году и пробегу аналог считается «похожим»
YEAR_WINDOW = 1
MILEAGE_WINDOW_KM = 50_000


def select_comparables(car: Car, pool: list[Comparable]) -> list[Comparable]:
    same_model = [
        c for c in pool
        if c.make.lower() == car.make.lower() and c.model.lower() == car.model.lower()
    ]
    close = [
        c for c in same_model
        if abs(c.year - car.year) <= YEAR_WINDOW
        and abs(c.mileage_km - car.mileage_km) <= MILEAGE_WINDOW_KM
    ]
    return close or same_model


def defect_cost(d: Defect, prices: dict[tuple[str, Severity], int]) -> int:
    """Выбранный вариант ремонта (база/подрядчик/интернет), иначе — прайс."""
    option = d.repair_option
    return option.total if option else prices.get((d.code, d.severity), 0)


def repair_cost(defects: list[Defect], prices: dict[tuple[str, Severity], int]) -> int:
    return sum(defect_cost(d, prices) for d in defects)


def estimate_price(
    car: Car,
    defects: list[Defect],
    pool: list[Comparable],
    prices: dict[tuple[str, Severity], int],
    currency: str = "KZT",
) -> PriceEstimate | None:
    """None, если аналогов нет: тогда цену вносит человек."""
    comps = select_comparables(car, pool)
    if not comps:
        return None

    values = sorted(c.price for c in comps)
    if len(values) >= 4:
        q1, _, q3 = quantiles(values, n=4)
        low, high = int(q1), int(q3)
    else:
        low, high = values[0], values[-1]
    mid = int(median(values))
    repair = repair_cost(defects, prices)

    return PriceEstimate(
        comparables_count=len(comps),
        market_low=low,
        market_median=mid,
        market_high=high,
        repair_cost=repair,
        offer_low=max(low - repair, 0),
        offer_high=max(mid - repair, 0),
        currency=currency,
    )
