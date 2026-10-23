"""Конвейер целиком с подставной моделью: без сети и без платных запросов."""

from carval.llm import sniff_media_type
from carval.models import (
    FoundDefect, Photo, Review, Severity, ShotQuality, PhotoIssue, ZoneInspection,
)
from carval.pipeline.run import analyze
from carval.report import TELEGRAM_LIMIT, render
from carval.storage import LocalStorage


class FakeLLM:
    """Отвечает заранее заготовленными объектами в зависимости от схемы."""

    def __init__(self):
        self.calls = []

    async def parse(self, *, model, system, content, schema, **kw):
        self.calls.append((schema.__name__, model))
        if schema is ShotQuality:
            return ShotQuality(unusable=[PhotoIssue(angle_id="rear", problem="Блик")])
        if schema is ZoneInspection:
            if "Кузов" in system:
                return ZoneInspection(
                    defects=[FoundDefect(code="dent", severity=Severity.moderate, angle_id="left",
                                         location="левая задняя дверь", description="вмятина",
                                         confidence=0.85)],
                    not_assessable=["Перекрас — проверить толщиномером"],
                )
            return ZoneInspection()
        if schema is Review:
            return Review(overall_confidence=0.7, summary="Ок")
        raise AssertionError(schema)


async def test_analyze_end_to_end(settings, catalog, camry):
    storage = LocalStorage(settings.data_dir / "local")
    photos = []
    for angle in ["front", "left", "rear", "wheel_fl"]:
        key = await storage.save_photo("case1", angle, b"\xff\xd8fake-jpeg")
        photos.append(Photo(angle_id=angle, storage_key=key))

    llm = FakeLLM()
    report = await analyze(camry, photos, catalog=catalog, llm=llm, storage=storage, settings=settings)

    assert "rear_left" in report.missing_angles
    assert [i.angle_id for i in report.photo_issues] == ["rear"]
    assert len(report.defects) == 1 and report.defects[0].zone == "body"
    # вмятина есть в своей базе — расчёт по выбранному варианту, а не по прайсу
    dent = report.defects[0]
    assert dent.repair_option.source == "own"
    assert report.estimate.repair_cost == dent.repair_option.total
    assert report.review.overall_confidence == 0.7

    # дешёвая модель только для контроля съёмки
    assert ("ShotQuality", settings.model_fast) in llm.calls
    assert ("ZoneInspection", settings.model_main) in llm.calls

    await storage.save_report(report)
    assert (await storage.get_report(report.id)).defects[0].id == report.defects[0].id

    text = render(report, catalog)
    assert "Вмятина" in text and "Проверить вручную" in text
    assert len(text) <= TELEGRAM_LIMIT


def test_sniff_media_type():
    assert sniff_media_type(b"\x89PNG\r\n") == "image/png"
    assert sniff_media_type(b"RIFF1234WEBPVP8") == "image/webp"
    assert sniff_media_type(b"\xff\xd8\xff") == "image/jpeg"
