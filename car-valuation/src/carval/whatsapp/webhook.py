"""Приём сообщений от WhatsApp: проверка подписи, разбор в понятный формат.

Разбор вынесен в чистые функции (verify_signature, parse_webhook) отдельно
от веб-сервера — их можно проверить без поднятия HTTP, в обычных тестах.
Сервер — на aiohttp, он уже используется ботом через aiogram, лишней
зависимости не добавляет.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable
from enum import Enum

from aiohttp import web
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    text = "text"
    image = "image"
    audio = "audio"
    document = "document"
    other = "other"


class IncomingMessage(BaseModel):
    wa_message_id: str
    from_phone: str  # E.164 без '+', как прислал WhatsApp
    from_name: str = ""
    type: MessageType
    text: str = ""
    media_id: str | None = None
    timestamp: str = ""


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """X-Hub-Signature-256: sha256=<hex>. Без него (или без настроенного секрета)
    отклоняем — иначе кто угодно сможет слать поддельные сообщения в систему."""
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def parse_webhook(payload: dict) -> list[IncomingMessage]:
    """Формат Meta: entry[].changes[].value.messages[]. Один запрос может
    нести несколько сообщений (редко) или ни одного (статусы доставки —
    их тоже присылают на тот же вебхук, пропускаем молча)."""
    out: list[IncomingMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                mtype = m.get("type", "other")
                text = ""
                media_id = None
                if mtype == "text":
                    text = m.get("text", {}).get("body", "")
                elif mtype in ("image", "audio", "document"):
                    media_id = m.get(mtype, {}).get("id")
                    text = m.get(mtype, {}).get("caption", "")
                elif mtype == "button":
                    text = m.get("button", {}).get("text", "")
                try:
                    kind = MessageType(mtype)
                except ValueError:
                    kind = MessageType.other
                out.append(IncomingMessage(
                    wa_message_id=m.get("id", ""),
                    from_phone=m.get("from", ""),
                    from_name=contacts.get(m.get("from"), ""),
                    type=kind,
                    text=text,
                    media_id=media_id,
                    timestamp=m.get("timestamp", ""),
                ))
    return out


def make_app(*, verify_token: str, app_secret: str,
             on_message: Callable[[IncomingMessage], Awaitable[None]]) -> web.Application:
    """on_message вызывается на каждое входящее сообщение — туда подключается
    роутинг лидов (leads.py) и дальше агент или уведомление менеджеру."""

    async def verify(request: web.Request) -> web.Response:
        if (request.query.get("hub.mode") == "subscribe"
                and request.query.get("hub.verify_token") == verify_token):
            return web.Response(text=request.query.get("hub.challenge", ""))
        return web.Response(status=403, text="verify_token не совпадает")

    async def receive(request: web.Request) -> web.Response:
        body = await request.read()
        if not verify_signature(app_secret, body, request.headers.get("X-Hub-Signature-256")):
            logger.warning("WhatsApp webhook: неверная подпись запроса")
            return web.Response(status=403, text="bad signature")
        payload = await request.json()
        for msg in parse_webhook(payload):
            try:
                await on_message(msg)
            except Exception:
                logger.exception("Ошибка обработки сообщения %s от %s", msg.wa_message_id, msg.from_phone)
        return web.Response(text="OK")  # ответ 200 за секунды, иначе Meta повторяет доставку

    app = web.Application()
    app.router.add_get("/webhook/whatsapp", verify)
    app.router.add_post("/webhook/whatsapp", receive)
    return app
