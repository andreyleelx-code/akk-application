"""Запуск: python -m carval.whatsapp.main (или carval-whatsapp после установки).

Это приём сообщений, определение ответственного менеджера и короткое
подтверждение клиенту, что сообщение получено — то, что можно включить
уже сейчас, с настоящим номером WhatsApp. Полноценный агент с бронью
(как в demo/agent.html: find_available_cars, get_quote, create_booking_request)
подключается отдельным шагом, когда календарь берётся из RentProg, а не
придумывается — см. docs/09-whatsapp-setup.md.
"""

from __future__ import annotations

import logging

from aiohttp import web

from ..leads import LeadRouter
from ..settings import get_settings
from .client import WhatsAppClient
from .router import looks_like_payment, route_message
from .webhook import IncomingMessage, make_app

logger = logging.getLogger(__name__)


def build_app() -> web.Application:
    settings = get_settings()
    if not settings.manager_list:
        raise SystemExit("Не задан CARVAL_WHATSAPP_MANAGERS в .env, например: Ерлан,Дана,Арман")
    if not settings.whatsapp_verify_token:
        raise SystemExit("Не задан WHATSAPP_VERIFY_TOKEN в .env — придумайте строку и впишите её же при подписке вебхука в Meta")

    router = LeadRouter(settings.manager_list, work_hours=(settings.whatsapp_work_from, settings.whatsapp_work_to))
    client = WhatsAppClient(settings)

    async def on_message(msg: IncomingMessage) -> None:
        lead = route_message(msg, router)
        logger.info("Лид от %s (%s) -> %s%s", msg.from_phone, msg.from_name or "без имени",
                    lead.assigned_to, " [отвечает агент]" if lead.handled_by_agent else "")
        if looks_like_payment(msg):
            logger.info("Похоже на запись об оплате от %s — показать %s для подтверждения суммы", msg.from_phone, lead.assigned_to)

        if not client.enabled:
            return  # без ключа — только маршрутизация и логи, без ответа клиенту
        reply = (
            "Добрый вечер! Сейчас нерабочее время, но ваше сообщение получено. Отвечу утром."
            if lead.handled_by_agent
            else f"Спасибо, ваше сообщение получил менеджер {lead.assigned_to}. Он ответит в ближайшее время."
        )
        try:
            await client.send_text(msg.from_phone, reply)
        except Exception:
            logger.exception("Не удалось отправить подтверждение в WhatsApp")

    return make_app(verify_token=settings.whatsapp_verify_token, app_secret=settings.whatsapp_app_secret, on_message=on_message)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    web.run_app(build_app(), port=8080)


if __name__ == "__main__":
    run()
