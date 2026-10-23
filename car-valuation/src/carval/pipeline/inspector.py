"""Шаг 2. Дефектоскопы по зонам: кузов, оптика, колёса, салон, подкапотное."""

from __future__ import annotations

import asyncio

from ..catalog import Catalog
from ..llm import LLM, image_block, text_block
from ..models import Car, Defect, ZoneInspection
from ..settings import Settings
from . import load_prompt


def _car_line(car: Car) -> str:
    mileage = f"{car.mileage_km:,}".replace(",", " ")
    return f"{car.make} {car.model}, {car.year} г., пробег {mileage} км"


async def inspect_zone(
    zone: str,
    photos: list[tuple[str, bytes]],
    *,
    car: Car,
    catalog: Catalog,
    llm: LLM,
    settings: Settings,
) -> tuple[list[Defect], list[str]]:
    codes = catalog.defects.get(zone, {})
    system = load_prompt(
        settings,
        "defect_inspector",
        zone_name=catalog.zones.get(zone, zone),
        defect_list="\n".join(f"- `{c}` — {name}" for c, name in codes.items()),
        car=_car_line(car),
    )
    content: list[dict] = []
    for angle_id, data in photos:
        spec = catalog.angle(angle_id)
        content.append(text_block(f"[{angle_id}] {spec.title if spec else angle_id}"))
        content.append(image_block(data))
    content.append(text_block("Осмотри зону и перечисли дефекты."))

    result = await llm.parse(
        model=settings.model_main, system=system, content=content,
        schema=ZoneInspection, effort="high",
    )
    defects = [Defect(zone=zone, **d.model_dump()) for d in result.defects]
    return defects, result.not_assessable


async def inspect_all(
    zone_photos: dict[str, list[tuple[str, bytes]]],
    *,
    car: Car,
    catalog: Catalog,
    llm: LLM,
    settings: Settings,
) -> tuple[list[Defect], list[str]]:
    results = await asyncio.gather(*(
        inspect_zone(zone, photos, car=car, catalog=catalog, llm=llm, settings=settings)
        for zone, photos in zone_photos.items() if photos
    ))
    defects = [d for ds, _ in results for d in ds]
    notes = [n for _, ns in results for n in ns]
    return defects, notes
