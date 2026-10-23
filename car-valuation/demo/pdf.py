"""PDF-версия презентации для пересылки (WhatsApp, почта).

    python demo/pdf.py demo/presentation-silkway.html "Silk Way — ИИ-осмотр.pdf"

Тёмная тема и фирменные цвета сохраняются, оглавление и кнопки убираются.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

CSS = """
nav.toc,.no-print,.agenda{display:none!important}
.layout{grid-template-columns:minmax(0,1fr)!important;padding-block:0!important}
main section{break-before:auto;padding-top:24px}
h2,h3,.eyebrow{break-after:avoid}
.card,.kpi,.step,tr,.phone,.msg,figure,img{break-inside:avoid}
"""


async def main(src: Path, out: Path) -> None:
    async with async_playwright() as p:
        chrome = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")  # как в build.py
        browser = await p.chromium.launch(executable_path=str(chrome) if chrome.exists() else None)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(src.resolve().as_uri())
        await page.emulate_media(media="screen", color_scheme="dark")
        await page.add_style_tag(content=CSS)
        await page.wait_for_timeout(1200)  # дорисовать графики и чаты
        await page.pdf(path=str(out), width="1280px", height="1810px", print_background=True,
                       margin={"top": "28px", "bottom": "28px", "left": "32px", "right": "32px"})
        await browser.close()


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/presentation.html")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else src.with_suffix(".pdf"))
    asyncio.run(main(src, out))
    print("Готово:", out)
