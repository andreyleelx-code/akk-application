from io import BytesIO

from PIL import Image

from carval.llm import MAX_SIDE, image_block, prepare_image
from carval.models import (
    Car, Defect, DefectStatus, PriceEstimate, Report, Review, Settlement, Severity,
)
from carval.pipeline.decision import needs_manual_review

CAR = Car(vin_or_plate="x", make="A", model="B", year=2020, mileage_km=1)
EST = PriceEstimate(comparables_count=5, market_low=1, market_median=2, market_high=3,
                    repair_cost=0, offer_low=1, offer_high=2)


def d(sev=Severity.minor, conf=0.9, status=DefectStatus.confirmed):
    return Defect(zone="body", code="dent", severity=sev, angle_id="left", location="x",
                  description="", confidence=conf, status=status)


def report(**kw):
    base = dict(car=CAR, estimate=EST, review=Review(overall_confidence=0.9, summary=""))
    base.update(kw)
    return Report(**base)


def test_clean_report_passes():
    assert not needs_manual_review(report(defects=[d()]))


def test_rules_that_require_manual_review():
    assert needs_manual_review(report(defects=[d(Severity.severe)]))
    assert needs_manual_review(report(defects=[d(conf=0.5, status=DefectStatus.pending)]))
    assert needs_manual_review(report(review=Review(overall_confidence=0.5, summary="")))
    assert needs_manual_review(report(missing_angles=["rear"]))
    assert needs_manual_review(report(estimate=None))
    assert needs_manual_review(report(kind="return", estimate=None, settlement=Settlement(due=1000)))


def test_rejected_severe_does_not_trigger():
    assert not needs_manual_review(report(defects=[d(Severity.severe, status=DefectStatus.rejected)]))


def test_return_within_deposit_passes():
    assert not needs_manual_review(report(kind="return", estimate=None, settlement=Settlement(total=10, deposit=30)))


def jpeg(w, h):
    b = BytesIO(); Image.new("RGB", (w, h), (90, 90, 90)).save(b, format="JPEG"); return b.getvalue()


def test_big_photo_is_downscaled():
    out = prepare_image(jpeg(4000, 3000))
    assert max(Image.open(BytesIO(out)).size) == MAX_SIDE
    assert image_block(jpeg(4000, 3000))["source"]["media_type"] == "image/jpeg"


def test_small_photo_untouched():
    data = jpeg(800, 600)
    assert prepare_image(data) is data
