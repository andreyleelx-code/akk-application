"""Разметка фото: рамки и номера дефектов поверх снимка.

Номер на фото совпадает с номером дефекта в отчёте, цвет — со степенью:
жёлтый — лёгкий, оранжевый — средний, красный — серьёзный, серый — отклонён.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .models import Defect, DefectStatus, Report, Severity

COLORS = {
    Severity.minor: (242, 184, 7),
    Severity.moderate: (240, 112, 24),
    Severity.severe: (220, 38, 38),
}
REJECTED = (150, 150, 150)
FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "arialbd.ttf",
    "Arial Bold.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def annotate(image: bytes, defects: list[tuple[int, Defect]]) -> bytes:
    """Рисует рамки дефектов (номер, дефект) на одном фото. Возвращает JPEG."""
    img = Image.open(BytesIO(image)).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    line = max(3, w // 250)
    font = _font(max(16, w // 40))

    for number, d in defects:
        if not d.box:
            continue
        x, y, bw, bh = d.box
        x0, y0 = max(0, x * w), max(0, y * h)
        x1, y1 = min(w - 1, (x + bw) * w), min(h - 1, (y + bh) * h)
        color = REJECTED if d.status == DefectStatus.rejected else COLORS[d.severity]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=line)

        label = str(number)
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
        r = max(tw, th) // 2 + line * 2
        cx, cy = x0, y0
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(255, 255, 255), width=2)
        draw.text((cx, cy), label, fill=(255, 255, 255), font=font, anchor="mm")

    out = BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def defects_by_photo(report: Report) -> dict[str, list[tuple[int, Defect]]]:
    """{angle_id: [(номер в отчёте, дефект)]} — только фото, где есть рамки."""
    grouped: dict[str, list[tuple[int, Defect]]] = {}
    for i, d in enumerate(report.defects, 1):
        if d.box:
            grouped.setdefault(d.angle_id, []).append((i, d))
    return grouped
