from carval.models import (
    Car, Defect, RepairOption, Report, ScoutOffer, ScoutResult, Severity,
)
from carval.parts import attach_options, choose_option, needs_parts
from carval.pipeline.parts_scout import scout
from carval.pricing import repair_cost


def defect(code="dent", severity=Severity.moderate):
    return Defect(zone="body", code=code, severity=severity, angle_id="left",
                  location="x", description="", confidence=0.9)


def opt(total, source="own", days=1, kind="repair"):
    return RepairOption(kind=kind, supplier="s", source=source, labor_cost=total, days=days)


def test_choose_cheapest_then_fastest():
    assert choose_option([opt(50), opt(30, days=3), opt(30, days=1)]) == 2


def test_web_price_never_beats_base():
    assert choose_option([opt(50), opt(10, source="web")]) == 0


def test_web_used_when_base_empty():
    assert choose_option([opt(40, source="web"), opt(30, source="web")]) == 1


def test_attach_options_from_example_base(catalog, camry):
    report = Report(car=camry, defects=[defect("dent"), defect("tire_wear")])
    uncovered = attach_options(report, catalog.suppliers)
    dent = report.defects[0]
    assert dent.options and dent.repair_option.source == "own"
    assert [d.code for d in uncovered] == ["tire_wear"]


def test_repair_cost_uses_chosen_option(catalog):
    d = defect()
    d.options, d.chosen = [opt(12_345)], 0
    assert repair_cost([d], catalog.repair_prices) == 12_345
    d.chosen = None
    assert repair_cost([d], catalog.repair_prices) == catalog.repair_prices[("dent", Severity.moderate)]


def test_informational_defects_need_no_parts(catalog):
    assert not needs_parts(defect("paint_mismatch"), catalog.repair_prices)
    assert needs_parts(defect("tire_wear"), catalog.repair_prices)


class SearchLLM:
    async def search(self, **kw):
        return "найдено: шины на kolesa.kz", ["https://kolesa.kz/a/show/1"]

    async def parse(self, *, schema, content, **kw):
        did = content[0]["text"].split("id дефектов: ")[1].split("\n")[0]
        return ScoutResult(offers=[
            ScoutOffer(defect_id=did, kind="used", supplier="kolesa.kz", url="https://kolesa.kz/a/show/1",
                       parts_kzt=40_000, note="пара б/у"),
            ScoutOffer(defect_id=did, kind="analog", supplier="выдумка", url="https://fake.example/x",
                       parts_kzt=1),
        ])


async def test_scout_keeps_only_urls_from_search(settings, camry):
    d = defect("tire_wear")
    await scout([d], car=camry, defect_names={d.id: "Износ"}, llm=SearchLLM(), settings=settings)
    assert [o.supplier for o in d.options] == ["kolesa.kz"]
    assert d.repair_option.source == "web" and "работа не найдена" in d.repair_option.note
