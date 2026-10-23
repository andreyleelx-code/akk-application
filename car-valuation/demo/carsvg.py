"""Демо-иллюстрации машин с нарисованными повреждениями.

Это не фото, а условные картинки для показа: как программа размечает
дефекты и как выглядит отчёт. Все виды — в кадре 800×450.
"""

from __future__ import annotations

W, H = 800, 450


def _shade(hex_color: str, k: float) -> str:
    """k<1 темнее, k>1 светлее."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    if k >= 1:
        r, g, b = (int(c + (255 - c) * (k - 1)) for c in (r, g, b))
    else:
        r, g, b = (int(c * k) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _scene(uid: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
  <linearGradient id="sky{uid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#c9d6df"/><stop offset="1" stop-color="#eef1f2"/>
  </linearGradient>
  <linearGradient id="lot{uid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#9a9d9f"/><stop offset="1" stop-color="#6e7173"/>
  </linearGradient>
  <linearGradient id="glass{uid}" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="#5b6d7a"/><stop offset="0.55" stop-color="#26323b"/><stop offset="1" stop-color="#1a2228"/>
  </linearGradient>
  <radialGradient id="rim{uid}" cx="0.4" cy="0.35" r="0.8">
    <stop offset="0" stop-color="#f4f6f7"/><stop offset="0.6" stop-color="#b5bcc1"/><stop offset="1" stop-color="#7d868c"/>
  </radialGradient>
  <radialGradient id="dent{uid}" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#000" stop-opacity="0.55"/><stop offset="0.6" stop-color="#000" stop-opacity="0.22"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="haze{uid}" cx="0.5" cy="0.5" r="0.6">
    <stop offset="0" stop-color="#f3e7b5" stop-opacity="0.85"/><stop offset="1" stop-color="#d9c98a" stop-opacity="0.55"/>
  </radialGradient>
</defs>
<rect width="{W}" height="300" fill="url(#sky{uid})"/>
<rect y="300" width="{W}" height="150" fill="url(#lot{uid})"/>
<path d="M0 300 H{W}" stroke="#8a8d8f" stroke-width="2"/>
<path d="M40 430 L180 360 M300 440 L360 362 M520 440 L470 362 M760 430 L640 360" stroke="#d8d8c8" stroke-width="4" opacity="0.5"/>
{body}
</svg>"""


def _wheel(uid: str, cx: float, cy: float, r: float = 52, worn: bool = False) -> str:
    rim = r * 0.64
    spokes = "".join(
        f'<path d="M{cx} {cy} L{cx + rim * 0.92 * c:.1f} {cy + rim * 0.92 * s:.1f}" stroke="#8e979c" stroke-width="{r * 0.13:.1f}" stroke-linecap="round"/>'
        for c, s in [(1, 0), (0.309, 0.951), (-0.809, 0.588), (-0.809, -0.588), (0.309, -0.951)]
    )
    import math
    tread = "".join(
        f'<path d="M{cx + (r - 1) * math.cos(a):.1f} {cy + (r - 1) * math.sin(a):.1f} L{cx + (r - 7) * math.cos(a):.1f} {cy + (r - 7) * math.sin(a):.1f}" stroke="#3a3a3a" stroke-width="2.4" opacity="{0.25 if worn and math.sin(a) > -0.2 else 0.9}"/>'
        for a in [i * math.pi / 18 for i in range(36)]
    )
    return f"""<g>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="#161616"/>
{tread}
<circle cx="{cx}" cy="{cy}" r="{rim}" fill="url(#rim{uid})" stroke="#5c6368" stroke-width="2"/>
<circle cx="{cx}" cy="{cy}" r="{rim * 0.72:.1f}" fill="#2a2e31"/>
{spokes}
<circle cx="{cx}" cy="{cy}" r="{r * 0.15:.1f}" fill="#c9cfd3" stroke="#6b7378"/>
</g>"""


# ---------------- Виды ----------------


def side(uid: str, color: str, mirror: bool = False, damage: str = "", worn_front: bool = False) -> str:
    dark, light = _shade(color, 0.72), _shade(color, 1.25)
    body = f"""
<defs><linearGradient id="paint{uid}" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{light}"/><stop offset="0.45" stop-color="{color}"/><stop offset="1" stop-color="{dark}"/>
</linearGradient></defs>
<ellipse cx="400" cy="388" rx="330" ry="16" fill="#000" opacity="0.28"/>
<g {'transform="translate(800 0) scale(-1 1)"' if mirror else ''}>
<path d="M95 330 C85 300 90 282 110 276 L245 258 C270 252 290 248 305 244 L380 186 C400 176 430 172 470 172 L560 174 C590 176 610 186 630 204 L668 240 L720 246 C735 250 742 262 740 285 L738 320 C736 334 728 338 715 338 L648 338 A58 58 0 0 0 532 338 L268 338 A58 58 0 0 0 152 338 L120 338 C100 338 95 336 95 330 Z"
  fill="url(#paint{uid})" stroke="{dark}" stroke-width="2"/>
<path d="M318 246 L388 194 C405 186 430 182 470 182 L552 184 C578 186 596 196 612 210 L640 240 Z" fill="url(#glass{uid})"/>
<rect x="470" y="182" width="11" height="62" fill="{dark}"/>
<path d="M330 250 L326 334 M478 248 L478 336 M625 245 L632 334" stroke="{dark}" stroke-width="2.2" fill="none"/>
<path d="M112 292 C300 286 560 282 736 284" stroke="{light}" stroke-width="2" fill="none" opacity="0.8"/>
<rect x="430" y="262" width="30" height="7" rx="3.5" fill="{dark}"/>
<rect x="580" y="259" width="30" height="7" rx="3.5" fill="{dark}"/>
<path d="M318 236 C326 226 344 226 348 234 L346 246 L322 248 Z" fill="{dark}"/>
<path d="M108 278 L168 268 L162 284 L104 292 Z" fill="#eef3f6" stroke="#9aa3a8"/>
<path d="M724 250 L740 256 L740 282 L720 278 Z" fill="#b3161b" stroke="#6b0c0f"/>
<path d="M104 318 L150 318" stroke="#2a2a2a" stroke-width="5" stroke-linecap="round" opacity="0.6"/>
{_wheel(uid, 210, 334, worn=worn_front)}
{_wheel(uid, 590, 334)}
{damage}
</g>"""
    return _scene(uid, body)


def front(uid: str, color: str, damage: str = "", plate: str = "123 ABC 02") -> str:
    dark, light = _shade(color, 0.72), _shade(color, 1.25)
    body = f"""
<defs><linearGradient id="paint{uid}" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{light}"/><stop offset="0.5" stop-color="{color}"/><stop offset="1" stop-color="{dark}"/>
</linearGradient></defs>
<ellipse cx="400" cy="392" rx="300" ry="16" fill="#000" opacity="0.28"/>
<rect x="148" y="320" width="70" height="72" rx="12" fill="#161616"/>
<rect x="582" y="320" width="70" height="72" rx="12" fill="#161616"/>
<path d="M262 104 L538 104 C552 104 560 110 566 120 L612 214 L188 214 L234 120 C240 110 248 104 262 104 Z" fill="url(#paint{uid})" stroke="{dark}" stroke-width="2"/>
<path d="M272 122 L528 122 L584 212 L216 212 Z" fill="url(#glass{uid})"/>
<path d="M180 204 L150 200 C140 200 138 214 148 218 L186 222 Z" fill="{dark}"/>
<path d="M620 204 L650 200 C660 200 662 214 652 218 L614 222 Z" fill="{dark}"/>
<path d="M170 214 L630 214 C658 220 670 240 668 270 L664 340 C662 352 650 358 638 358 L162 358 C150 358 138 352 136 340 L132 270 C130 240 142 220 170 214 Z" fill="url(#paint{uid})" stroke="{dark}" stroke-width="2"/>
<path d="M180 232 C300 222 500 222 620 232" stroke="{light}" stroke-width="2" fill="none"/>
<path d="M156 246 L292 256 L286 280 L162 274 C150 272 148 252 156 246 Z" fill="#eef3f6" stroke="#8d969b" stroke-width="2"/>
<path d="M644 246 L508 256 L514 280 L638 274 C650 272 652 252 644 246 Z" fill="#eef3f6" stroke="#8d969b" stroke-width="2"/>
<circle cx="196" cy="262" r="10" fill="#fff" stroke="#b7c0c5"/><circle cx="604" cy="262" r="10" fill="#fff" stroke="#b7c0c5"/>
<rect x="318" y="262" width="164" height="40" rx="10" fill="#22272b"/>
<path d="M326 274 H474 M326 284 H474 M326 294 H474" stroke="#4b5459" stroke-width="2"/>
<circle cx="400" cy="282" r="9" fill="#c9cfd3"/>
<rect x="250" y="318" width="300" height="26" rx="8" fill="#2b3033"/>
<rect x="346" y="321" width="108" height="21" rx="3" fill="#f7f7f2" stroke="#333"/>
<text x="400" y="337" font-family="DejaVu Sans, Arial, sans-serif" font-size="13" font-weight="700" text-anchor="middle" fill="#111">{plate}</text>
{damage}"""
    return _scene(uid, body)


def rear(uid: str, color: str, damage: str = "", plate: str = "123 ABC 02") -> str:
    dark, light = _shade(color, 0.72), _shade(color, 1.25)
    body = f"""
<defs><linearGradient id="paint{uid}" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{light}"/><stop offset="0.5" stop-color="{color}"/><stop offset="1" stop-color="{dark}"/>
</linearGradient></defs>
<ellipse cx="400" cy="392" rx="300" ry="16" fill="#000" opacity="0.28"/>
<rect x="148" y="320" width="70" height="72" rx="12" fill="#161616"/>
<rect x="582" y="320" width="70" height="72" rx="12" fill="#161616"/>
<path d="M270 112 L530 112 C544 112 552 118 558 128 L600 214 L200 214 L242 128 C248 118 256 112 270 112 Z" fill="url(#paint{uid})" stroke="{dark}" stroke-width="2"/>
<path d="M280 128 L520 128 L570 206 L230 206 Z" fill="url(#glass{uid})"/>
<path d="M170 214 L630 214 C658 220 670 240 668 270 L664 340 C662 352 650 358 638 358 L162 358 C150 358 138 352 136 340 L132 270 C130 240 142 220 170 214 Z" fill="url(#paint{uid})" stroke="{dark}" stroke-width="2"/>
<path d="M150 236 L300 240 L298 266 L156 268 C146 266 144 242 150 236 Z" fill="#b3161b" stroke="#6b0c0f" stroke-width="2"/>
<path d="M650 236 L500 240 L502 266 L644 268 C654 266 656 242 650 236 Z" fill="#b3161b" stroke="#6b0c0f" stroke-width="2"/>
<path d="M300 246 L500 246" stroke="#7c1013" stroke-width="5"/>
<path d="M210 228 C330 222 470 222 590 228" stroke="{light}" stroke-width="2" fill="none"/>
<rect x="346" y="276" width="108" height="24" rx="3" fill="#f7f7f2" stroke="#333"/>
<text x="400" y="294" font-family="DejaVu Sans, Arial, sans-serif" font-size="14" font-weight="700" text-anchor="middle" fill="#111">{plate}</text>
<path d="M150 318 C300 312 500 312 650 318 L646 344 C644 352 636 356 626 356 L174 356 C164 356 156 352 154 344 Z" fill="{dark}"/>
{damage}"""
    return _scene(uid, body)


def wheel_close(uid: str, color: str, damage: str = "", worn: bool = False) -> str:
    dark = _shade(color, 0.72)
    body = f"""
<path d="M0 0 H800 V150 C700 150 640 110 400 100 C160 110 100 150 0 150 Z" fill="{color}"/>
<path d="M150 210 C170 120 280 70 400 70 C520 70 630 120 650 210" fill="none" stroke="{dark}" stroke-width="18"/>
<ellipse cx="400" cy="432" rx="230" ry="16" fill="#000" opacity="0.35"/>
<g transform="translate(400 250) scale(2.6) translate(-400 -250)">{_wheel(uid, 400, 250, 58, worn=worn)}</g>
{damage}"""
    return _scene(uid, body)


# ---------------- Повреждения ----------------


def dent(uid: str, cx, cy, rx, ry) -> str:
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#dent{uid})"/>'
            f'<path d="M{cx - rx * 0.7} {cy - ry * 0.55} Q{cx} {cy - ry * 1.05} {cx + rx * 0.7} {cy - ry * 0.55}" '
            f'stroke="#fff" stroke-width="2" opacity="0.45" fill="none"/>')


def scratch(x1, y1, x2, y2, n: int = 3) -> str:
    out = []
    for i in range(n):
        dy = i * 3 - n
        out.append(f'<path d="M{x1} {y1 + dy} Q{(x1 + x2) / 2} {(y1 + y2) / 2 + dy + 4} {x2} {y2 + dy}" '
                   f'stroke="#ffffff" stroke-width="{1.6 - i * 0.3:.1f}" opacity="0.85" fill="none"/>')
    out.append(f'<path d="M{x1} {y1 + 1} Q{(x1 + x2) / 2} {(y1 + y2) / 2 + 5} {x2} {y2 + 1}" stroke="#333" stroke-width="0.8" opacity="0.6" fill="none"/>')
    return "".join(out)


def chips(points) -> str:
    return "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#e9ecee" stroke="#555" stroke-width="0.6"/>' for x, y, r in points)


def glass_chip(cx, cy) -> str:
    rays = "".join(f'<path d="M{cx} {cy} L{cx + dx} {cy + dy}" stroke="#eaf3f8" stroke-width="1.4"/>'
                   for dx, dy in [(9, -4), (-7, -8), (-9, 5), (6, 9), (2, -11)])
    return f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="#dfeef6" opacity="0.9"/>{rays}'


def crack(points, color: str = "#f2f2f2", width: float = 2) -> str:
    d = "M" + " L".join(f"{x} {y}" for x, y in points)
    return f'<path d="{d}" stroke="{color}" stroke-width="{width}" fill="none" stroke-linejoin="bevel"/>'


def tint(path_d: str, color: str, opacity: float = 0.35) -> str:
    return f'<path d="{path_d}" fill="{color}" opacity="{opacity}"/>'


def rust(spots) -> str:
    out = []
    for x, y, r in spots:
        out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#8a3b12" opacity="0.85"/>')
        out.append(f'<circle cx="{x + r * 0.3}" cy="{y - r * 0.2}" r="{r * 0.55:.1f}" fill="#c0601f" opacity="0.8"/>')
    return "".join(out)


def haze(uid: str, cx, cy, rx, ry) -> str:
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#haze{uid})"/>'


def gap(points, width: float = 5) -> str:
    d = "M" + " L".join(f"{x} {y}" for x, y in points)
    return f'<path d="{d}" stroke="#141414" stroke-width="{width}" fill="none" opacity="0.85"/>'


def curb_rash(cx, cy, r, a0, a1) -> str:
    import math
    out = []
    for i in range(14):
        a = a0 + (a1 - a0) * i / 13
        x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a)
        x2, y2 = cx + (r - 9) * math.cos(a + 0.03), cy + (r - 9) * math.sin(a + 0.03)
        out.append(f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" stroke="#5a5f62" stroke-width="2.4"/>')
    return "".join(out)
