from carval.catalog import Comparable
from carval.models import Car, Defect, DefectStatus, Report, Severity
from carval.pricing import estimate_price, repair_cost, select_comparables


def defect(code="dent", severity=Severity.moderate, status=DefectStatus.pending, zone="body"):
    return Defect(zone=zone, code=code, severity=severity, angle_id="left",
                  location="левая дверь", description="", confidence=0.9, status=status)


def test_repair_prices_cover_every_defect_code(catalog):
    for zone, codes in catalog.defects.items():
        for code in codes:
            for sev in Severity:
                assert (code, sev) in catalog.repair_prices, f"{zone}:{code}:{sev.value}"


def test_select_prefers_close_year_and_mileage(camry, catalog):
    comps = select_comparables(camry, catalog.comparables)
    assert comps and all(c.model == "Camry" for c in comps)
    assert all(abs(c.year - 2018) <= 1 for c in comps)


def test_select_falls_back_to_same_model():
    car = Car(vin_or_plate="x", make="Toyota", model="Camry", year=2005, mileage_km=400_000)
    pool = [Comparable("Toyota", "Camry", 2019, 50_000, 10)]
    assert select_comparables(car, pool) == pool


def test_no_comparables_means_no_estimate(catalog):
    car = Car(vin_or_plate="x", make="Lada", model="Niva", year=2015, mileage_km=1)
    assert estimate_price(car, [], catalog.comparables, catalog.repair_prices) is None


def test_offer_is_market_minus_repair(camry, catalog):
    d = [defect("dent", Severity.moderate)]
    est = estimate_price(camry, d, catalog.comparables, catalog.repair_prices)
    assert est.repair_cost == catalog.repair_prices[("dent", Severity.moderate)]
    assert est.offer_high == est.market_median - est.repair_cost
    assert est.offer_low == est.market_low - est.repair_cost
    assert est.market_low <= est.market_median <= est.market_high


def test_offer_never_negative():
    car = Car(vin_or_plate="x", make="A", model="B", year=2000, mileage_km=1)
    pool = [Comparable("A", "B", 2000, 1, 100)]
    est = estimate_price(car, [defect()], pool, {("dent", Severity.moderate): 1000})
    assert est.offer_low == 0 and est.offer_high == 0


def test_rejected_defects_excluded(camry):
    report = Report(car=camry, defects=[defect(), defect(status=DefectStatus.rejected)])
    prices = {("dent", Severity.moderate): 100}
    assert repair_cost(report.active_defects, prices) == 100
