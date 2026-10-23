"""Сквозной сценарий проката: акт выдачи сохраняется, при возврате находится по номеру."""

from carval.models import Defect, DefectStatus, RentalInfo, Report, Severity
from carval.pipeline.decision import needs_manual_review
from carval.rental import load_terms, settle
from carval.storage import LocalStorage


def dent(box, sev=Severity.minor):
    return Defect(zone="body", code="dent", severity=sev, angle_id="left", location="дверь",
                  description="", confidence=0.9, box=box, status=DefectStatus.confirmed)


async def test_handover_then_return(settings, catalog, camry):
    repo = LocalStorage(settings.data_dir / "local")
    out = Report(kind="handover", car=camry, defects=[dent([0.1, 0.1, 0.1, 0.1])],
                 rental=RentalInfo(deposit=30_000, days=1, km_out=1_000))
    await repo.save_report(out)
    await repo.save_report(Report(kind="buyback", car=camry))  # чужой тип не мешает

    found = await repo.find_latest(camry.vin_or_plate, "handover")
    assert found.id == out.id

    new = dent([0.6, 0.6, 0.1, 0.1])
    ret = Report(kind="return", car=camry, defects=[dent([0.11, 0.1, 0.1, 0.1]), new],
                 rental=RentalInfo(km_in=1_150, handover_report_id=found.id))
    ret.settlement = settle(ret, found, catalog, load_terms(settings))
    assert ret.settlement.new_defect_ids == [new.id]
    assert ret.settlement.refund == 30_000 - ret.settlement.total

    # оценщик отклонил новую находку — удерживать нечего
    new.status = DefectStatus.rejected
    ret.settlement = settle(ret, found, catalog, load_terms(settings))
    assert ret.settlement.total == 0 and ret.settlement.refund == 30_000
    assert not needs_manual_review(ret)
