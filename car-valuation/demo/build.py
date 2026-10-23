"""Собирает демо: картинки машин, разметку дефектов, отчёты и единый HTML-файл.

Запуск из папки car-valuation:
    python demo/build.py

Что получается (всё в папке demo/):
    cars/<машина>/<ракурс>.jpg         «фото» машины (условная иллюстрация)
    cars/<машина>/marked/<ракурс>.jpg  то же фото с рамками дефектов — так их рисует программа
    reports/<машина>.json              отчёт в формате программы
    presentation.html                  всё в одном файле: демо, расчёты, документация

Дефекты и проценты — примерные. Цена, вычет на ремонт, рамки и текст отчёта
посчитаны настоящим кодом программы (pricing.py, annotate.py, report.py).
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(DEMO))

import carsvg as c  # noqa: E402
from PIL import Image  # noqa: E402

from carval.annotate import annotate, defects_by_photo  # noqa: E402
from carval.catalog import load_catalog  # noqa: E402
from carval.models import (  # noqa: E402
    Car, Defect, DefectStatus, Photo, Report, Review, ReviewFinding, Severity,
)
from carval.pricing import estimate_price, select_comparables  # noqa: E402
from carval.report import render  # noqa: E402
from carval.settings import Settings  # noqa: E402

C, M, S = Severity.minor, Severity.moderate, Severity.severe
OK, NO, WAIT = DefectStatus.confirmed, DefectStatus.rejected, DefectStatus.pending


@dataclass
class D:
    """Демо-дефект: что нарисовать на картинке и где рамка (в пикселях кадра 800×450)."""

    angle: str
    zone: str
    code: str
    sev: Severity
    conf: float
    location: str
    desc: str
    box: tuple[int, int, int, int]
    draw: str = ""
    status: DefectStatus = WAIT


@dataclass
class DemoCar:
    id: str
    car: Car
    color: str
    plate: str
    views: dict[str, str]  # angle_id -> название вида
    defects: list[D]
    not_assessable: list[str] = field(default_factory=list)
    manual_notes: list[str] = field(default_factory=list)
    review: Review | None = None
    story: str = ""
    worn: bool = False


def mbox(x, y, w, h):
    """Рамка для зеркального вида (правый бок): x отражается."""
    return (800 - x - w, y, w, h)


# ---------------- Три демо-машины ----------------

CAMRY = DemoCar(
    id="camry",
    car=Car(vin_or_plate="731 KZA 02", make="Toyota", model="Camry", year=2018, mileage_km=110_000),
    color="#e4e7ea", plate="731 KZA 02",
    views={"front": "Спереди", "left": "Левый бок", "right": "Правый бок", "rear": "Сзади", "wheel_fl": "Колесо переднее левое"},
    story="Типичный случай: ИИ нашёл скрытый перекрас по разнотону, толщиномер подтвердил. Одна находка оказалась бликом — оценщик её отклонил.",
    worn=True,
    defects=[
        D("left", "body", "dent", M, 0.88, "левая задняя дверь, середина", "Вмятина ~8 см без повреждения ЛКП",
          (512, 262, 96, 62), c.dent("camry", 560, 292, 36, 23), OK),
        D("left", "body", "paint_mismatch", M, 0.58, "левое переднее крыло", "Оттенок крыла теплее, чем у двери",
          (150, 244, 180, 60),
          c.tint("M168 270 L318 250 L326 298 L270 300 A58 58 0 0 0 166 300 Z", "#f3d9a4", 0.55), OK),
        D("left", "body", "scratch", C, 0.74, "передний бампер слева", "Поверхностная царапина ~15 см",
          (98, 284, 90, 28), c.scratch(108, 300, 178, 294, 4), OK),
        D("front", "glass_lights", "glass_chip", C, 0.92, "лобовое стекло, зона пассажира", "Скол ~5 мм, без трещин",
          (310, 140, 42, 42), c.glass_chip(331, 161), OK),
        D("wheel_fl", "wheels", "tire_wear", M, 0.81, "шина переднего левого колеса", "Протектор ~2,5 мм, нужна замена пары",
          (246, 258, 308, 150), "", OK),
        D("right", "body", "scratch", C, 0.41, "правая передняя дверь", "Возможная царапина",
          mbox(330, 254, 90, 30), "", NO),
    ],
    not_assessable=[
        "Разнотон левого переднего крыла — проверить толщиномером",
        "Двигатель и КПП — проверить OBD-сканером",
    ],
    manual_notes=[
        "Толщиномер: левое переднее крыло 240–260 мкм (остальные 110–130) — перекрас",
        "OBD: ошибок нет",
    ],
    review=Review(
        overall_confidence=0.82,
        summary="Перекрас крыла подтверждён замером. Вероятен лёгкий ремонт передней части, остальное соответствует пробегу.",
        findings=[
            ReviewFinding(note="Разнотон (58%) подтверждён толщиномером: проверьте крепления крыла и лонжерон."),
            ReviewFinding(note="Износ шин соответствует пробегу 110 000 км."),
        ],
    ),
)

TUCSON = DemoCar(
    id="tucson",
    car=Car(vin_or_plate="455 HTA 01", make="Hyundai", model="Tucson", year=2020, mileage_km=85_000),
    color="#24456e", plate="455 HTA 01",
    views={"front": "Спереди", "left": "Левый бок", "right": "Правый бок", "rear": "Сзади", "wheel_rr": "Колесо заднее правое"},
    story="Машина в хорошем состоянии, дефекты косметические. Все находки ждут решения оценщика: нажмите ✓ или ✕ и посмотрите, как меняется цена.",
    defects=[
        D("rear", "body", "crack_bumper", M, 0.83, "задний бампер, справа от номера", "Трещина пластика ~10 см",
          (446, 308, 56, 52), c.crack([(462, 320), (474, 330), (468, 338), (486, 346), (480, 354)], "#0d0d0d", 2.6)),
        D("front", "glass_lights", "headlight_haze", C, 0.71, "правая фара", "Помутнение рассеивателя",
          (146, 238, 156, 50), c.haze("tucson", 222, 264, 70, 15)),
        D("front", "body", "chip", C, 0.66, "капот, передняя кромка", "Несколько сколов ЛКП",
          (344, 214, 96, 26), c.chips([(358, 226, 2.6), (372, 230, 2.2), (392, 224, 2.0), (421, 228, 2.8)])),
        D("wheel_rr", "wheels", "rim_damage", C, 0.79, "диск заднего правого колеса", "Задиры кромки диска о бордюр",
          (440, 204, 72, 132), c.curb_rash(400, 250, 96, -0.35, 0.9)),
    ],
    not_assessable=["Подвеска и рулевое управление — осмотр на подъёмнике"],
    review=Review(
        overall_confidence=0.88,
        summary="Дефекты косметические, признаков ДТП не видно.",
        findings=[ReviewFinding(note="Аналогов всего 4 — диапазон цены широкий, сверьте с базой компании.")],
    ),
)

RIO = DemoCar(
    id="rio",
    car=Car(vin_or_plate="102 KRA 05", make="Kia", model="Rio", year=2016, mileage_km=160_000),
    color="#b3202a", plate="102 KRA 05",
    views={"front": "Спереди", "left": "Левый бок", "right": "Правый бок", "rear": "Сзади"},
    story="Рискованный случай. Серьёзная вмятина и неровный зазор капота в одной зоне — признаки ДТП. Система ставит пометку «проверить вручную».",
    defects=[
        D("right", "body", "dent", S, 0.90, "правое переднее крыло над аркой", "Глубокая вмятина с заломом металла",
          mbox(200, 256, 110, 66), c.dent("rio", 255, 288, 44, 28) + c.scratch(225, 280, 285, 296, 2), OK),
        D("front", "body", "panel_gap", S, 0.64, "зазор капот — левое крыло", "Зазор шире с одной стороны",
          (168, 212, 146, 34), c.gap([(176, 233), (230, 228), (306, 224)], 6), WAIT),
        D("left", "body", "rust", M, 0.87, "задняя арка и порог слева", "Очаги коррозии",
          (612, 304, 70, 52), c.rust([(646, 330, 6), (660, 322, 4.5), (638, 338, 5), (668, 334, 3.5)]), OK),
        D("rear", "glass_lights", "light_crack", M, 0.80, "правый задний фонарь", "Трещина корпуса фонаря",
          (526, 234, 60, 40), c.crack([(540, 244), (556, 252), (548, 260), (572, 264)], "#ffe1e1", 2), WAIT),
        D("right", "body", "scratch", M, 0.76, "правая задняя дверь", "Глубокая царапина до грунта ~40 см",
          mbox(482, 286, 140, 30), c.scratch(490, 300, 612, 296, 4), WAIT),
    ],
    not_assessable=[
        "Геометрия кузова после возможного ДТП — проверка на стапеле",
        "Пробег 160 000 км: износ салона сверить с одометром",
    ],
    review=Review(
        overall_confidence=0.55,
        summary="Признаки ДТП в передней части. Отчёт нельзя утверждать без осмотра.",
        findings=[
            ReviewFinding(note="Неровный зазор капота и серьёзная вмятина правого крыла — вероятно ДТП, проверьте лонжероны."),
            ReviewFinding(note="Зазор капота найден с уверенностью 64%, но сильно влияет на цену — подтвердите вручную."),
            ReviewFinding(note="Вычет на ремонт ~7% рыночной цены: проверьте прайс на крыло."),
        ],
    ),
)

CARS = [CAMRY, TUCSON, RIO]


def demo_manual_rule(report: Report) -> bool:
    """Пример правила для показа (то же правило повторено на странице).
    В программе правило задаётся в src/carval/pipeline/decision.py."""
    serious = any(d.severity == S and d.status != NO for d in report.defects)
    unsure = any(d.status == WAIT and d.confidence < 0.6 for d in report.defects)
    low_trust = report.review is not None and report.review.overall_confidence < 0.7
    return serious or unsure or low_trust


# ---------------- Картинки ----------------


def draw_view(car: DemoCar, angle: str) -> str:
    dmg = "".join(d.draw for d in car.defects if d.angle == angle)
    uid = f"{car.id}{angle}"
    # повреждения внутри зеркального вида нарисованы в исходных координатах
    if angle == "left":
        return c.side(uid, car.color, damage=dmg)
    if angle == "right":
        return c.side(uid, car.color, mirror=True, damage=dmg)
    if angle == "front":
        return c.front(uid, car.color, damage=dmg, plate=car.plate)
    if angle == "rear":
        return c.rear(uid, car.color, damage=dmg, plate=car.plate)
    return c.wheel_close(uid, car.color, damage=dmg, worn=car.worn)


async def render_jpegs(svgs: dict[Path, str]) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        chrome = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        browser = await p.chromium.launch(executable_path=str(chrome) if chrome.exists() else None)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        for path, svg in svgs.items():
            big = svg.replace('width="800" height="450"', 'width="1280" height="720"')
            await page.set_content(f"<body style='margin:0'>{big}</body>")
            await page.screenshot(path=str(path), type="jpeg", quality=88, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
        await browser.close()


def data_uri(jpeg: bytes, width: int = 560) -> str:
    img = Image.open(BytesIO(jpeg))
    img.thumbnail((width, width))
    out = BytesIO()
    img.save(out, format="JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


# ---------------- Сборка ----------------


def build() -> None:
    settings = Settings(_env_file=None)
    catalog = load_catalog(settings)

    svgs: dict[tuple[str, str], str] = {}
    files: dict[Path, str] = {}
    for car in CARS:
        (DEMO / "cars" / car.id / "marked").mkdir(parents=True, exist_ok=True)
        for angle in car.views:
            svgs[(car.id, angle)] = draw_view(car, angle)
            files[DEMO / "cars" / car.id / f"{angle}.jpg"] = svgs[(car.id, angle)]
    asyncio.run(render_jpegs(files))

    (DEMO / "reports").mkdir(exist_ok=True)
    payload = []
    for car in CARS:
        defects = [
            Defect(zone=d.zone, code=d.code, severity=d.sev, angle_id=d.angle, location=d.location,
                   description=d.desc, confidence=d.conf, status=d.status,
                   box=[round(d.box[0] / 800, 4), round(d.box[1] / 450, 4),
                        round(d.box[2] / 800, 4), round(d.box[3] / 450, 4)])
            for d in car.defects
        ]
        photos = [Photo(angle_id=a, storage_key=f"cars/{car.id}/{a}.jpg") for a in car.views]
        report = Report(id=f"demo-{car.id}", car=car.car, photos=photos, defects=defects,
                        not_assessable=car.not_assessable, manual_notes=car.manual_notes,
                        review=car.review)
        report.needs_manual_review = demo_manual_rule(report)
        report.estimate = estimate_price(report.car, report.active_defects, catalog.comparables,
                                         catalog.repair_prices, settings.currency)
        (DEMO / "reports" / f"{car.id}.json").write_text(report.model_dump_json(indent=2), "utf-8")

        marked = {}
        for angle, items in defects_by_photo(report).items():
            raw = (DEMO / "cars" / car.id / f"{angle}.jpg").read_bytes()
            out = annotate(raw, items)
            (DEMO / "cars" / car.id / "marked" / f"{angle}.jpg").write_bytes(out)
            marked[angle] = data_uri(out)

        comps = select_comparables(report.car, catalog.comparables)
        payload.append({
            "id": car.id,
            "story": car.story,
            "car": report.car.model_dump(),
            "views": [{"angle": a, "title": t, "svg": svgs[(car.id, a)]} for a, t in car.views.items()],
            "defects": [
                {**d.model_dump(mode="json"),
                 "name": catalog.defect_name(d.zone, d.code),
                 "zone_name": catalog.zones[d.zone],
                 "cost": catalog.repair_prices.get((d.code, d.severity), 0),
                 "status": d.status.value}
                for d in report.defects
            ],
            "estimate": report.estimate.model_dump(),
            "comparables": [{"make": x.make, "model": x.model, "year": x.year, "mileage_km": x.mileage_km, "price": x.price} for x in comps],
            "not_assessable": report.not_assessable,
            "manual_notes": report.manual_notes,
            "review": report.review.model_dump() if report.review else None,
            "needs_manual_review": report.needs_manual_review,
            "telegram_text": render(report, catalog),
            "marked": marked,
        })
        print(f"{car.id}: {len(defects)} дефектов, предложение "
              f"{report.estimate.offer_low:,}–{report.estimate.offer_high:,} ₸".replace(",", " "))

    template = (DEMO / "template.html").read_text("utf-8")
    html = template.replace("/*__DEMO_DATA__*/null", json.dumps(payload, ensure_ascii=False))
    # Для публикации ссылкой — фрагмент (обёртку добавляет сервис)
    (DEMO / ".artifact.html").write_text(html, "utf-8")
    # Для ноутбука на встрече — полный документ, работает без интернета
    out = DEMO / "presentation.html"
    out.write_text('<!doctype html>\n<html lang="ru">\n' + html + "\n</html>\n", "utf-8")
    print(f"Готово: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    build()
