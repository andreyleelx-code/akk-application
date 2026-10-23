from carval.models import Defect, DefectStatus, RentalInfo, Report, Severity
from carval.rental import load_terms, settle, was_there


def d(code="scratch", angle="left", box=(0.5, 0.5, 0.1, 0.1), sev=Severity.minor, status=DefectStatus.confirmed):
    return Defect(zone="body", code=code, severity=sev, angle_id=angle, location="x", description="",
                  confidence=0.9, box=list(box) if box else None, status=status)


def test_same_place_is_old_damage():
    assert was_there(d(box=(0.52, 0.5, 0.1, 0.1)), [d()])


def test_other_place_or_type_is_new():
    assert not was_there(d(box=(0.1, 0.1, 0.1, 0.1)), [d()])
    assert not was_there(d(code="dent"), [d()])
    assert not was_there(d(angle="right"), [d()])


def test_settlement_charges_only_new_damage_and_fees(settings, catalog, camry):
    terms = load_terms(settings)
    out = Report(kind="handover", car=camry, defects=[d()],
                 rental=RentalInfo(deposit=30000, days=2, body="crossover", km_out=10_000))
    new_dent = d(code="dent", box=(0.1, 0.1, 0.1, 0.1), sev=Severity.moderate)
    ret = Report(kind="return", car=camry, defects=[d(), new_dent],
                 rental=RentalInfo(km_in=10_520, dirty=True, fuel_missing_l=10))
    s = settle(ret, out, catalog, terms)
    assert s.new_defect_ids == [new_dent.id]
    assert s.repair == catalog.repair_prices[("dent", Severity.moderate)]
    assert s.extra_km == 120 and s.extra_km_cost == 120 * terms.extra_km_kzt
    assert s.wash == terms.wash_kzt["crossover"]
    assert s.total == s.repair + s.wash + s.extra_km_cost + s.fuel
    assert s.refund == max(30000 - s.total, 0) and s.due == max(s.total - 30000, 0)


def test_clean_return_refunds_full_deposit(settings, catalog, camry):
    out = Report(kind="handover", car=camry, defects=[d()], rental=RentalInfo(deposit=30000, km_out=1))
    ret = Report(kind="return", car=camry, defects=[d()], rental=RentalInfo(km_in=100))
    s = settle(ret, out, catalog, load_terms(settings))
    assert s.total == 0 and s.refund == 30000
