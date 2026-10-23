"""Калибровка на прошлых сделках: где ИИ ошибается и насколько.

Запуск:  python -m carval.backtest            (все кейсы из data/cases)
         python -m carval.backtest case_017   (один кейс)

Формат кейса — см. data/cases/README.md. Результат: data/backtest_results.csv
и сводка в консоли. Каждый прогон — платные запросы к Claude API.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

import yaml

from .catalog import load_catalog
from .llm import LLM
from .models import Car, Photo, Report
from .pipeline.run import analyze
from .settings import get_settings

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class FolderStorage:
    """Читает фото прямо из папки кейса (storage_key = путь к файлу)."""

    async def load_photo(self, key: str) -> bytes:
        return Path(key).read_bytes()


def load_case(folder: Path) -> tuple[Car, list[Photo], dict]:
    meta = yaml.safe_load((folder / "case.yaml").read_text("utf-8"))
    photos = [
        Photo(angle_id=f.stem, storage_key=str(f), media_type=MEDIA[f.suffix.lower()])
        for f in sorted(folder.iterdir()) if f.suffix.lower() in IMAGE_EXT
    ]
    return Car(**meta["car"]), photos, meta


def compare(report: Report, meta: dict) -> dict:
    found = {(d.zone, d.code) for d in report.active_defects}
    known = {(d["zone"], d["code"]) for d in meta.get("known_defects", [])}
    est = report.estimate
    actual = meta.get("actual_price")
    row = {
        "case": meta.get("id", ""),
        "car": f"{report.car.make} {report.car.model} {report.car.year}",
        "found": len(found),
        "known": len(known),
        "missed": "; ".join(f"{z}:{c}" for z, c in sorted(known - found)),
        "extra": "; ".join(f"{z}:{c}" for z, c in sorted(found - known)),
        "offer_low": est.offer_low if est else "",
        "offer_high": est.offer_high if est else "",
        "actual_price": actual or "",
        "price_error_pct": "",
        "confidence": round(report.review.overall_confidence, 2) if report.review else "",
    }
    if est and actual:
        mid = (est.offer_low + est.offer_high) / 2
        row["price_error_pct"] = round((mid - actual) / actual * 100, 1)
    return row


async def run(only: str | None = None) -> None:
    settings = get_settings()
    catalog = load_catalog(settings)
    llm = LLM(settings.anthropic_api_key)
    storage = FolderStorage()

    root = settings.data_dir / "cases"
    folders = [f for f in sorted(root.iterdir()) if (f / "case.yaml").exists()]
    if only:
        folders = [f for f in folders if f.name == only]
    if not folders:
        raise SystemExit(f"Нет кейсов в {root}. Формат — data/cases/README.md")

    rows = []
    for folder in folders:
        car, photos, meta = load_case(folder)
        meta.setdefault("id", folder.name)
        print(f"→ {folder.name}: {len(photos)} фото")
        report = await analyze(car, photos, catalog=catalog, llm=llm, storage=storage, settings=settings)
        rows.append(compare(report, meta))

    out = settings.data_dir / "backtest_results.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    missed = sum(len(r["missed"].split("; ")) for r in rows if r["missed"])
    known = sum(r["known"] for r in rows)
    errors = [abs(r["price_error_pct"]) for r in rows if r["price_error_pct"] != ""]
    print(f"\nКейсов: {len(rows)}")
    if known:
        print(f"Пропущено известных дефектов: {missed} из {known} ({missed / known:.0%})")
    if errors:
        print(f"Средняя ошибка цены: {sum(errors) / len(errors):.1f}%")
    print(f"Подробно: {out}")


def main() -> None:
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else None))


if __name__ == "__main__":
    main()
