from io import BytesIO

from PIL import Image

from carval.annotate import COLORS, REJECTED, annotate, defects_by_photo
from carval.models import Car, Defect, DefectStatus, Report, Severity


def jpeg(w=400, h=300) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (w, h), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def defect(box, severity=Severity.severe, status=DefectStatus.pending, angle="left"):
    return Defect(zone="body", code="dent", severity=severity, angle_id=angle, location="x",
                  description="", confidence=0.9, box=box, status=status)


def close(a, b, tol=40):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_box_drawn_in_severity_color():
    out = Image.open(BytesIO(annotate(jpeg(), [(1, defect([0.5, 0.5, 0.25, 0.25]))])))
    # правая граница рамки: x = 0.75 * 400 = 300, середина по высоте
    assert close(out.getpixel((299, 340 // 2 + 30)), COLORS[Severity.severe])


def test_rejected_defect_is_grey():
    d = defect([0.5, 0.5, 0.25, 0.25], status=DefectStatus.rejected)
    out = Image.open(BytesIO(annotate(jpeg(), [(1, d)])))
    assert close(out.getpixel((299, 200)), REJECTED)


def test_defect_without_box_leaves_photo_unchanged():
    out = Image.open(BytesIO(annotate(jpeg(), [(1, defect(None))])))
    assert close(out.getpixel((200, 150)), (128, 128, 128), tol=6)


def test_defects_grouped_by_photo_keep_report_numbers():
    car = Car(vin_or_plate="x", make="A", model="B", year=2020, mileage_km=1)
    report = Report(car=car, defects=[
        defect([0.1, 0.1, 0.1, 0.1], angle="left"),
        defect(None, angle="left"),
        defect([0.2, 0.2, 0.1, 0.1], angle="front"),
    ])
    grouped = defects_by_photo(report)
    assert [n for n, _ in grouped["left"]] == [1]
    assert [n for n, _ in grouped["front"]] == [3]
