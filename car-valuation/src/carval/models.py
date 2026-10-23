"""Модели данных: машина, фото, дефекты, оценка, отчёт."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from typing import Literal

from pydantic import BaseModel, Field, computed_field


class Severity(str, Enum):
    minor = "minor"
    moderate = "moderate"
    severe = "severe"


class DefectStatus(str, Enum):
    pending = "pending"  # нашёл ИИ, человек ещё не смотрел
    confirmed = "confirmed"  # оценщик подтвердил
    rejected = "rejected"  # оценщик отклонил (ложное срабатывание)
    manual = "manual"  # добавил человек (ИИ не увидел)


class Car(BaseModel):
    vin_or_plate: str
    make: str
    model: str
    year: int
    mileage_km: int


class Photo(BaseModel):
    angle_id: str
    storage_key: str  # путь в хранилище (локально или Supabase Storage)
    media_type: str = "image/jpeg"


class AngleSpec(BaseModel):
    id: str
    zone: str
    title: str
    required: bool = True


# ---------- Ответы моделей (структурированный вывод) ----------


class PhotoIssue(BaseModel):
    angle_id: str
    problem: str = Field(description="Что не так: размыто, темно, блик, не тот ракурс")


class ShotQuality(BaseModel):
    """Ответ контролёра съёмки."""

    unusable: list[PhotoIssue] = Field(default_factory=list)


class RepairOption(BaseModel):
    """Вариант устранения дефекта: ремонт, замена оригиналом, аналогом или б/у."""

    kind: Literal["repair", "oem", "analog", "used"]
    supplier: str
    source: Literal["own", "contractor", "web"]  # своя база, подрядчик, найдено в интернете
    parts_cost: int = 0
    labor_cost: int = 0
    days: int | None = None
    url: str | None = None
    note: str = ""

    @computed_field
    @property
    def total(self) -> int:
        return self.parts_cost + self.labor_cost


class Defect(BaseModel):
    zone: str
    code: str = Field(description="Код дефекта из справочника зоны")
    severity: Severity
    angle_id: str = Field(description="На каком фото виден дефект")
    location: str = Field(description="Где именно: 'левое переднее крыло, над аркой'")
    description: str
    confidence: float = Field(ge=0, le=1, description="Уверенность 0..1")
    box: list[float] | None = Field(
        None,
        description="Рамка дефекта на фото в долях от размера кадра: [x, y, ширина, высота], каждое 0..1",
    )
    status: DefectStatus = DefectStatus.pending
    options: list[RepairOption] = Field(default_factory=list)
    chosen: int | None = None  # индекс выбранного варианта в options
    id: str = Field(default_factory=lambda: uuid4().hex[:8])


    @property
    def repair_option(self) -> RepairOption | None:
        if self.chosen is None or not 0 <= self.chosen < len(self.options):
            return None
        return self.options[self.chosen]


class FoundDefect(BaseModel):
    """Дефект в ответе модели (без служебных полей)."""

    code: str
    severity: Severity
    angle_id: str
    location: str
    description: str
    confidence: float = Field(ge=0, le=1)
    box: list[float] | None = Field(
        None,
        description="Рамка дефекта на фото в долях от размера кадра: [x, y, ширина, высота], каждое 0..1",
    )


class ZoneInspection(BaseModel):
    """Ответ дефектоскопа по одной зоне."""

    defects: list[FoundDefect] = Field(default_factory=list)
    not_assessable: list[str] = Field(
        default_factory=list,
        description="Что нельзя оценить по этим фото и нужно проверить вручную",
    )


class ScoutOffer(BaseModel):
    """Предложение, найденное в интернете (ответ разборщика результатов поиска)."""

    defect_id: str
    kind: Literal["repair", "oem", "analog", "used"]
    supplier: str = Field(description="Магазин или мастерская")
    url: str = Field(description="Страница, где найдена цена")
    parts_kzt: int = Field(0, description="Цена детали, ₸; 0 если это только работа")
    labor_kzt: int = Field(0, description="Цена работы, ₸; 0 если не найдена")
    note: str = Field("", description="Что именно: 'фонарь б/у, левый, Алматы'")


class ScoutResult(BaseModel):
    offers: list[ScoutOffer] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    defect_id: str | None = Field(None, description="id дефекта, если замечание о нём")
    note: str


class Review(BaseModel):
    """Ответ ревьюера."""

    findings: list[ReviewFinding] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)
    summary: str


# ---------- Расчёт и отчёт ----------


class PriceEstimate(BaseModel):
    comparables_count: int
    market_low: int
    market_median: int
    market_high: int
    repair_cost: int
    offer_low: int
    offer_high: int
    currency: str = "KZT"


class Report(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    car: Car
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    photos: list[Photo] = Field(default_factory=list)
    missing_angles: list[str] = Field(default_factory=list)
    photo_issues: list[PhotoIssue] = Field(default_factory=list)
    defects: list[Defect] = Field(default_factory=list)
    not_assessable: list[str] = Field(default_factory=list)
    estimate: PriceEstimate | None = None
    review: Review | None = None
    manual_notes: list[str] = Field(default_factory=list)  # толщиномер, OBD, VIN
    needs_manual_review: bool = True
    approved_price: int | None = None
    approved_by: int | None = None

    @property
    def active_defects(self) -> list[Defect]:
        """Дефекты, которые идут в расчёт (без отклонённых)."""
        return [d for d in self.defects if d.status != DefectStatus.rejected]
