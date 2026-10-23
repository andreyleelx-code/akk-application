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
    Car, Defect, DefectStatus, Photo, RepairOption, Report, Review, ReviewFinding, Severity,
)
from carval.parts import KIND_RU, SOURCE_RU, attach_options, choose_option, needs_parts  # noqa: E402
from carval.pricing import defect_cost, estimate_price, select_comparables  # noqa: E402
from carval.models import RentalInfo  # noqa: E402
from carval.rental import load_terms, settle  # noqa: E402
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
    photo: str = ""  # файл фото в папке парка (фирменная версия)


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

FLEET_DIR: Path | None = None  # папка с фото парка, задаётся брендом
OUT_DIR = DEMO


def photo_b64(name: str) -> str:
    return base64.b64encode((FLEET_DIR / name).read_bytes()).decode()


FL = {"front_left": "Спереди-слева 45°"}

LC200 = DemoCar(
    id="lc200",
    car=Car(vin_or_plate="880 SWR 02", make="Toyota", model="Land Cruiser 200", year=2018, mileage_km=145_000),
    color="#111", plate="880 SWR 02", views=FL, photo="lc200.jpg",
    story="ИИ заметил разнотон переднего крыла — толщиномер подтвердил перекрас. Одна находка оказалась бликом на капоте, оценщик её отклонил.",
    defects=[
        D("front_left", "body", "dent", M, 0.86, "левая задняя дверь", "Вмятина ~8 см, ЛКП цел",
          (630, 224, 62, 44), c.p_dent(660, 245, 24, 16, True), OK),
        D("front_left", "body", "paint_mismatch", M, 0.57, "левое переднее крыло", "Оттенок крыла отличается от двери",
          (440, 195, 95, 70), c.p_tint("M445 205 L525 198 L530 255 L450 262 Z", "#7d8ea8", 0.22), OK),
        D("front_left", "body", "scratch", C, 0.78, "передний бампер слева", "Поверхностная царапина ~15 см",
          (100, 292, 100, 32), c.p_scratch([(110, 315), (150, 311), (190, 306)], 1.5, True), OK),
        D("front_left", "wheels", "rim_damage", C, 0.80, "диск переднего левого колеса", "Задиры кромки о бордюр",
          (440, 290, 112, 112), c.p_curb(495, 345, 46, -0.5, 1.0), OK),
        D("front_left", "glass_lights", "glass_chip", C, 0.90, "лобовое стекло", "Скол ~4 мм",
          (314, 78, 34, 34), c.p_chips([(330, 95, 2.0)]), OK),
        D("front_left", "body", "dent", C, 0.42, "капот", "Возможная вмятина",
          (200, 138, 80, 26), "", NO),
    ],
    not_assessable=["Разнотон переднего крыла — проверить толщиномером", "Рама и подвеска — осмотр на подъёмнике"],
    manual_notes=["Толщиномер: левое переднее крыло 260 мкм (остальные 120–140) — перекрас", "OBD: ошибок нет"],
    review=Review(overall_confidence=0.81,
                  summary="Перекрас крыла подтверждён замером. Остальные повреждения косметические.",
                  findings=[ReviewFinding(note="Разнотон (57%) подтверждён толщиномером: проверьте геометрию передней части."),
                            ReviewFinding(note="Находка «вмятина на капоте» (42%) — вероятно блик, оценщик отклонил.")]),
)

COBALT = DemoCar(
    id="cobalt",
    car=Car(vin_or_plate="531 SWR 02", make="Chevrolet", model="Cobalt", year=2022, mileage_km=98_000),
    color="#fff", plate="531 SWR 02", views=FL, photo="cobalt.jpg",
    story="Много косметики: вмятина, царапина, потёртый бампер, мутная фара и очаги ржавчины на пороге. Решения ждут оценщика — нажмите ✓ или ✕.",
    defects=[
        D("front_left", "body", "dent", M, 0.88, "левая передняя дверь", "Вмятина ~10 см",
          (513, 258, 64, 44), c.p_dent(545, 280, 26, 17), WAIT),
        D("front_left", "body", "scratch", M, 0.76, "левая задняя дверь", "Царапина до грунта ~30 см",
          (606, 276, 116, 32), c.p_scratch([(615, 300), (660, 296), (712, 290)], 1.6), WAIT),
        D("front_left", "body", "crack_bumper", M, 0.70, "передний бампер, низ слева", "Потёртости и трещина пластика",
          (52, 322, 76, 38), c.p_scuff(60, 330, 60, 22, 10, dark_paint=False), WAIT),
        D("front_left", "glass_lights", "headlight_haze", C, 0.73, "левая фара", "Помутнение рассеивателя",
          (252, 226, 98, 46), c.p_haze(300, 248, 44, 18), WAIT),
        D("front_left", "body", "rust", M, 0.84, "левый порог", "Очаги коррозии",
          (506, 324, 66, 26), c.p_rust([(520, 338, 3.5), (536, 341, 2.5), (556, 337, 3)]), WAIT),
    ],
    not_assessable=["Пробег 98 000 км: сверить с историей обслуживания"],
    review=Review(overall_confidence=0.79, summary="Дефекты косметические, признаков ДТП не видно.",
                  findings=[ReviewFinding(note="Ржавчина на пороге: проверьте снизу, нет ли сквозной коррозии.")]),
)

PHOTO_CARS = [LC200, COBALT]


# ---------------- Прокат: выдача и возврат ----------------


@dataclass
class RentalCase:
    id: str
    car: Car
    color: str
    plate: str
    body_type: str  # sedan | suv
    rental_body: str  # sedan | crossover | suv — для мойки
    views: dict[str, str]
    before: list[D]  # повреждения при выдаче
    new: list[D]  # появились за время аренды
    out: RentalInfo
    back: RentalInfo
    client: str
    when_out: str
    when_in: str
    story: str
    photo: str = ""


LIXIANG = RentalCase(
    id="l9", car=Car(vin_or_plate="702 SWR 02", make="Lixiang", model="L9", year=2024, mileage_km=15_880),
    color="#2b2f33", plate="702 SWR 02", body_type="suv", rental_body="suv",
    views={"front": "Спереди", "left": "Левый бок", "right": "Правый бок", "rear": "Сзади"},
    before=[
        D("front", "body", "chip", C, 0.84, "капот, передняя кромка", "Мелкие сколы ЛКП",
          (344, 212, 96, 28), c.chips([(358, 226, 2.6), (380, 230, 2.2), (414, 226, 2.6)]), OK),
        D("rear", "body", "scratch", C, 0.79, "задний бампер слева", "Поверхностная царапина",
          (176, 310, 88, 26), c.scratch(188, 326, 252, 322, 3), OK),
    ],
    new=[
        D("right", "body", "dent", C, 0.89, "правая задняя дверь", "Вмятина ~5 см без повреждения ЛКП",
          mbox(470, 258, 76, 52), c.dent("l9in", 508, 282, 28, 18), OK),
        D("front", "body", "scratch", C, 0.81, "передний бампер справа", "Поверхностная царапина ~20 см",
          (452, 316, 100, 28), c.scratch(462, 332, 540, 328, 4), OK),
    ],
    out=RentalInfo(client="А. Ахметов", deposit=50_000, days=3, body="suv", km_out=15_200),
    back=RentalInfo(km_in=15_880, dirty=True, fuel_missing_l=0),
    client="А. Ахметов", when_out="20.10 · 10:05", when_in="23.10 · 18:40",
    story="Клиент вернул машину с двумя мелкими новыми повреждениями, грязной и с перепробегом. Сколы на капоте и царапина на бампере были при выдаче — их ИИ не выставляет: это видно по акту выдачи.",
)

ELANTRA = RentalCase(
    id="elantra", car=Car(vin_or_plate="318 SWR 02", make="Hyundai", model="Elantra", year=2024, mileage_km=42_310),
    color="#e9ebed", plate="318 SWR 02", body_type="sedan", rental_body="sedan",
    views={"front": "Спереди", "left": "Левый бок", "right": "Правый бок", "rear": "Сзади"},
    before=[
        D("left", "body", "scratch", C, 0.77, "левая задняя дверь", "Лёгкая царапина",
          (488, 286, 82, 26), c.scratch(498, 300, 560, 298, 2), OK),
    ],
    new=[
        D("front", "glass_lights", "glass_crack", M, 0.93, "лобовое стекло, сторона водителя", "Трещина ~25 см от скола",
          (404, 128, 92, 78), c.crack([(420, 140), (446, 158), (438, 172), (478, 196)], "#f4f4f4", 1.8), OK),
        D("left", "body", "dent", C, 0.72, "левое переднее крыло", "Небольшая вмятина без повреждения ЛКП",
          (218, 270, 66, 40), c.dent("elin", 250, 290, 26, 16), OK),
    ],
    out=RentalInfo(client="Д. Сериков", deposit=30_000, days=1, body="sedan", km_out=42_100),
    back=RentalInfo(km_in=42_310, dirty=False, fuel_missing_l=8),
    client="Д. Сериков", when_out="22.10 · 09:30", when_in="23.10 · 10:15",
    story="Трещина лобового стекла дороже депозита: система показывает, сколько доплатить клиенту, и предлагает проверить, покрывает ли случай страховка.",
)

RENTALS = [LIXIANG, ELANTRA]

ZEEKR_X = RentalCase(
    id="zeekrx", car=Car(vin_or_plate="125 SWR 02", make="Zeekr", model="X", year=2024, mileage_km=18_640),
    color="#fff", plate="125 SWR 02", body_type="suv", rental_body="crossover", views=FL, photo="zeekr_x.jpg",
    before=[
        D("front_left", "body", "chip", C, 0.83, "капот, передняя часть", "Мелкие сколы ЛКП",
          (138, 172, 38, 28), c.p_chips([(150, 185, 1.6), (162, 190, 1.2)]), OK),
        D("front_left", "body", "scratch", C, 0.78, "передний бампер, нижняя часть", "Потёртости",
          (52, 314, 86, 30), c.p_scuff(60, 322, 70, 14, dark_paint=True), OK),
    ],
    new=[
        D("front_left", "glass_lights", "glass_crack", M, 0.93, "лобовое стекло, сторона пассажира", "Трещина ~20 см от удара камня",
          (270, 78, 168, 72), c.p_crack((380, 110), [[(345, 118), (310, 128), (280, 134)], [(405, 124), (428, 142)], [(368, 96), (356, 84)]]), OK),
        D("front_left", "body", "scratch", C, 0.80, "левая передняя дверь, низ", "Свежая царапина ~10 см",
          (460, 232, 110, 32), c.p_scratch([(470, 255), (520, 250), (560, 246)], 1.6), OK),
    ],
    out=RentalInfo(client="Д. Сериков", deposit=50_000, days=2, body="crossover", km_out=18_200),
    back=RentalInfo(km_in=18_640, dirty=False, fuel_missing_l=0),
    client="Д. Сериков", when_out="21.10 · 09:30", when_in="23.10 · 10:15",
    story="Трещина лобового стекла дороже депозита: система показывает, сколько доплатить клиенту, и предлагает проверить, покрывает ли случай страховка. Сколы и потёртости были при выдаче — их не выставляем.",
)

LIXIANG_PHOTO = RentalCase(
    id="l9", car=Car(vin_or_plate="702 SWR 02", make="Lixiang", model="L9", year=2024, mileage_km=15_880),
    color="#333", plate="702 SWR 02", body_type="suv", rental_body="suv", views=FL, photo="l9.jpg",
    before=[
        D("front_left", "body", "chip", C, 0.82, "капот", "Мелкие сколы ЛКП",
          (228, 168, 38, 26), c.p_chips([(240, 180, 1.5), (254, 184, 1.2)]), OK),
    ],
    new=[
        D("front_left", "body", "dent", C, 0.87, "левая передняя дверь", "Вмятина ~5 см без повреждения ЛКП",
          (535, 224, 62, 44), c.p_dent(565, 245, 24, 15, True), OK),
        D("front_left", "body", "scratch", C, 0.80, "передний бампер слева", "Поверхностная царапина ~15 см",
          (280, 306, 104, 34), c.p_scratch([(290, 330), (330, 325), (375, 318)], 1.5, True), OK),
    ],
    out=RentalInfo(client="А. Ахметов", deposit=50_000, days=3, body="suv", km_out=15_200),
    back=RentalInfo(km_in=15_880, dirty=True, fuel_missing_l=0),
    client="А. Ахметов", when_out="20.10 · 10:05", when_in="23.10 · 18:40",
    story="Клиент вернул машину с двумя мелкими новыми повреждениями, грязной и с перепробегом. Сколы на капоте были при выдаче — их ИИ не выставляет: это видно по акту выдачи.",
)

PHOTO_RENTALS = [LIXIANG_PHOTO, ZEEKR_X]


def rental_view(rc: RentalCase, angle: str, stage: str) -> str:
    items = rc.before + (rc.new if stage == "in" else [])
    dmg = "".join(d.draw for d in items if d.angle == angle)
    uid = f"{rc.id}{stage}{angle}"
    if rc.photo:
        return c.photo_scene(uid, photo_b64(rc.photo), dmg)
    if angle == "left":
        return c.side(uid, rc.color, damage=dmg, body_type=rc.body_type)
    if angle == "right":
        return c.side(uid, rc.color, mirror=True, damage=dmg, body_type=rc.body_type)
    if angle == "front":
        return c.front(uid, rc.color, damage=dmg, plate=rc.plate)
    return c.rear(uid, rc.color, damage=dmg, plate=rc.plate)


def to_defect(d: D) -> Defect:
    return Defect(zone=d.zone, code=d.code, severity=d.sev, angle_id=d.angle, location=d.location,
                  description=d.desc, confidence=d.conf, status=d.status,
                  box=[round(d.box[0] / 800, 4), round(d.box[1] / 450, 4), round(d.box[2] / 800, 4), round(d.box[3] / 450, 4)])


def build_rentals(settings: Settings, catalog) -> list[dict]:
    terms = load_terms(settings)
    out = []
    for rc in RENTALS:
        handover = Report(kind="handover", car=rc.car.model_copy(update={"mileage_km": rc.out.km_out}),
                          defects=[to_defect(d) for d in rc.before], rental=rc.out)
        # при возврате ИИ снова находит и старые повреждения: их отделяет сравнение с выдачей
        ret = Report(kind="return", car=rc.car, defects=[to_defect(d) for d in rc.before + rc.new],
                     rental=rc.back.model_copy(update={"handover_report_id": handover.id}))
        attach_options(ret, catalog.suppliers)
        ret.settlement = settle(ret, handover, catalog, terms)
        new_ids = set(ret.settlement.new_defect_ids)
        out.append({
            "id": rc.id, "story": rc.story, "car": rc.car.model_dump(), "client": rc.client,
            "when_out": rc.when_out, "when_in": rc.when_in, "km_out": rc.out.km_out, "km_in": rc.back.km_in,
            "days": rc.out.days, "body": rc.rental_body,
            "views": [{"angle": a, "title": t, "out": rental_view(rc, a, "out"), "in": rental_view(rc, a, "in")}
                      for a, t in rc.views.items()],
            "defects": [{**d.model_dump(mode="json"), "name": catalog.defect_name(d.zone, d.code),
                         "is_new": d.id in new_ids, "cost": defect_cost(d, catalog.repair_prices),
                         "option": ({**d.repair_option.model_dump(), "kind_ru": KIND_RU[d.repair_option.kind],
                                     "source_ru": SOURCE_RU[d.repair_option.source]} if d.repair_option else None)}
                        for d in ret.defects],
            "settlement": ret.settlement.model_dump(),
            "terms": {"km_per_day": terms.km_per_day, "extra_km_kzt": terms.extra_km_kzt,
                      "fuel_kzt_per_l": terms.fuel_kzt_per_l, "insurance_threshold": terms.insurance_threshold_kzt},
        })
        st = ret.settlement
        print(f"{rc.id}: новых {len(st.new_defect_ids)}, итого {st.total:,} ₸, вернуть {st.refund:,}, доплатить {st.due:,}".replace(",", " "))
    return out


def web(kind, supplier, url, parts, labor, note):
    """Пример того, что найдёт поиск в интернете. Сайты настоящие, цены условные."""
    return RepairOption(kind=kind, supplier=supplier, source="web", url=url,
                        parts_cost=parts, labor_cost=labor, note=note)


KOLESA, OLX, EZY, GIS = ("https://kolesa.kz/zapchasti/", "https://www.olx.kz/zapchasti/",
                         "https://ezyparts.kz", "https://2gis.kz/almaty")

# (машина, код дефекта) -> что «нашёл» поиск, если в базе пусто или для сравнения
WEB_OFFERS = {
    ("camry", "tire_wear"): [
        web("used", "kolesa.kz — объявления", KOLESA, 45_000, 0, "пара шин б/у 215/55 R17, Алматы · работа не найдена, уточнить"),
        web("analog", "Шинный магазин из 2GIS", GIS, 78_000, 8_000, "пара новых шин, бюджетный бренд, с монтажом"),
    ],
    ("rio", "light_crack"): [
        web("used", "kolesa.kz — авторазбор", KOLESA, 18_000, 0, "фонарь правый б/у, Kia Rio 2015–2017 · работа не найдена, уточнить"),
        web("analog", "Ezy Parts", EZY, 32_000, 0, "фонарь аналог, подбор по VIN · работа не найдена, уточнить"),
        web("used", "OLX.kz — объявления", OLX, 15_000, 0, "фонарь б/у, требует проверки креплений"),
    ],
    ("rio", "dent"): [
        web("used", "kolesa.kz — авторазбор", KOLESA, 25_000, 45_000, "крыло б/у в цвет + покраска у своего цеха"),
    ],
}


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
    if car.photo:
        return c.photo_scene(uid, photo_b64(car.photo), dmg)
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


# ---------------- Брендинг ----------------


def logo_svg(initials: str, accent: str, ink: str, size: int = 34) -> str:
    """Монограмма: инициалы компании на плашке фирменного цвета с отметкой-«галочкой осмотра»."""
    from html import escape
    return (f'<svg class="brand-logo" width="{size}" height="{size}" viewBox="0 0 40 40" aria-hidden="true">'
            f'<rect width="40" height="40" rx="10" fill="{accent}"/>'
            f'<path d="M27 29.5 L30 32.5 L35.5 26" stroke="{ink}" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<text x="18" y="25" text-anchor="middle" font-family="Onest, Golos Text, Arial, sans-serif" '
            f'font-size="{15 if len(initials) <= 2 else 12}" font-weight="800" fill="{ink}">{escape(initials)}</text></svg>')


BRAND_FILE = DEMO / "brand.json"


def apply_brand(html: str) -> str:
    from html import escape
    b = json.loads(BRAND_FILE.read_text("utf-8"))
    tag = (f"Демо для {b['company']} · цифры и фото условные" if b.get("for_client")
           else "Демо на примерах · цифры и фото условные")
    def file_or(key: str, fallback: str) -> str:
        f = b.get(key)
        return (BRAND_FILE.parent / f).read_text("utf-8").strip() if f else fallback

    mono = logo_svg(b["initials"], b["accent"], b["accent_ink"])
    logo, icon = file_or("logo_file", mono), file_or("logo_icon_file", mono)
    extra = ""
    if b.get("fonts_href"):
        extra += f'<link rel="stylesheet" href="{escape(b["fonts_href"])}">\n'
    css = []
    if b.get("theme"):
        tokens = "".join(f"{k}:{v};" for k, v in b["theme"].items())
        css.append(f":root{{{tokens}}}")
    if b.get("logo_is_wordmark"):
        css.append(".brand-name{display:none}")
    if b.get("road"):
        # пунктирная «дорога» через первый экран, как на сайте компании
        road = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 300' preserveAspectRatio='none'>"
                "<path d='M0 260 C300 200 520 170 760 175 C960 180 1080 120 1200 40' fill='none' "
                f"stroke='{b['accent']}' stroke-width='3' stroke-dasharray='22 18' opacity='0.4'/></svg>")
        from urllib.parse import quote
        css.append("#top{position:relative;overflow:hidden}#top::before{content:'';position:absolute;inset:auto 0 46% 0;"
                   f"height:300px;background:url(\"data:image/svg+xml,{quote(road)}\") no-repeat center/100% 100%;"
                   "pointer-events:none;z-index:0}#top>*{position:relative;z-index:1}"
                   ".hero h1{font-weight:900;letter-spacing:-.02em}"
                   ".tag.demo{background:transparent;border:1px solid var(--line);color:var(--ink);padding:5px 12px}"
                   ".lead,.hero p{text-shadow:0 0 12px var(--bg)}")
    if css:
        extra += "<style>" + "".join(css) + "</style>\n"
    values = {
        "{{BRAND_HEAD}}": extra,
        "{{LOGO}}": logo,
        "{{ICON}}": icon,
        "{{COMPANY}}": escape(b["company"]), "{{LEGAL}}": escape(b["legal"]),
        "{{DOMAIN}}": escape(b["domain"]), "{{HERO_TAG}}": escape(tag),
        "{{ACCENT}}": b["accent"], "{{ACCENT_INK}}": b["accent_ink"], "{{ACCENT_SOFT}}": b["accent_soft"],
    }
    for k, v in values.items():
        html = html.replace(k, v)
    return html


# ---------------- Сборка ----------------


def build() -> None:
    global CARS, RENTALS, FLEET_DIR, OUT_DIR
    OUT_DIR = DEMO
    settings = Settings(_env_file=None)
    catalog = load_catalog(settings)
    brand = json.loads(BRAND_FILE.read_text("utf-8"))
    if brand.get("fleet"):
        # фирменная версия: настоящие фото парка заказчика вместо рисунков
        FLEET_DIR = BRAND_FILE.parent / brand["fleet"]
        CARS, RENTALS = PHOTO_CARS, PHOTO_RENTALS
        OUT_DIR = FLEET_DIR / "build"  # фото заказчика не попадают в общую папку демо

    svgs: dict[tuple[str, str], str] = {}
    files: dict[Path, str] = {}
    for car in CARS:
        (OUT_DIR / "cars" / car.id / "marked").mkdir(parents=True, exist_ok=True)
        for angle in car.views:
            svgs[(car.id, angle)] = draw_view(car, angle)
            files[OUT_DIR / "cars" / car.id / f"{angle}.jpg"] = svgs[(car.id, angle)]
    asyncio.run(render_jpegs(files))

    (OUT_DIR / "reports").mkdir(exist_ok=True)
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
        # варианты ремонта: база поставщиков + примеры из интернета
        attach_options(report, catalog.suppliers)
        for d in report.defects:
            extra = WEB_OFFERS.get((car.id, d.code), [])
            if extra and needs_parts(d, catalog.repair_prices):
                d.options.extend(extra)
                d.chosen = choose_option(d.options)
        report.estimate = estimate_price(report.car, report.active_defects, catalog.comparables,
                                         catalog.repair_prices, settings.currency)
        (OUT_DIR / "reports" / f"{car.id}.json").write_text(report.model_dump_json(indent=2), "utf-8")

        marked = {}
        for angle, items in defects_by_photo(report).items():
            raw = (OUT_DIR / "cars" / car.id / f"{angle}.jpg").read_bytes()
            out = annotate(raw, items)
            (OUT_DIR / "cars" / car.id / "marked" / f"{angle}.jpg").write_bytes(out)
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
                 "options": [{**o.model_dump(), "kind_ru": KIND_RU[o.kind], "source_ru": SOURCE_RU[o.source]} for o in d.options],
                 "chosen": d.chosen,
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

    template = apply_brand((DEMO / "template.html").read_text("utf-8"))
    html = template.replace("/*__DEMO_DATA__*/null", json.dumps(payload, ensure_ascii=False))
    html = html.replace("/*__RENTAL_DATA__*/null", json.dumps(build_rentals(settings, catalog), ensure_ascii=False))
    if brand.get("fleet"):
        html = html.replace("Иллюстрации машин нарисованы для показа. В работе здесь будут фото с площадки, рамки рисует та же программа. Показаны 4–5 ключевых ракурсов из 27.",
                            "Фото — машины из парка компании, повреждения нанесены для примера. Рамки рисует программа. В работе будет 27 ракурсов, здесь показан один.")
    slug = json.loads(BRAND_FILE.read_text("utf-8")).get("slug")
    if slug:
        # Фирменная версия для конкретного заказчика: только файл, без публикации
        out = DEMO / f"presentation-{slug}.html"
    else:
        # Для публикации ссылкой — фрагмент (обёртку добавляет сервис)
        (DEMO / ".artifact.html").write_text(html, "utf-8")
        out = DEMO / "presentation.html"
    # Полный документ для ноутбука: работает без интернета
    out.write_text('<!doctype html>\n<html lang="ru">\n' + html + "\n</html>\n", "utf-8")
    print(f"Готово: {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    # python demo/build.py                         — нейтральная версия
    # python demo/build.py demo/brand-silkway.json — фирменная версия заказчика
    if len(sys.argv) > 1:
        BRAND_FILE = Path(sys.argv[1]).resolve()
    build()
