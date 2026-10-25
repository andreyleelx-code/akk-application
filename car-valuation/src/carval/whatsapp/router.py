"""Сообщение из WhatsApp -> лид -> тот же менеджер или агент.

Привязка к существующей сделке по номеру телефона (чтобы фото или оплата
легли в нужную карточку, а не повисли отдельно) появится вместе с
RentProg — см. docs/09-whatsapp-setup.md. Сейчас это только распределение
лида на менеджера/агента, тот же код, что проверен в tests/test_leads.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..leads import Channel, Lead, LeadRouter
from .webhook import IncomingMessage, MessageType

PAYMENT_WORDS = ("kaspi", "каспи", "оплат", "перевод", "чек", "депозит", "предоплат")


def lead_from_message(msg: IncomingMessage, at: datetime | None = None) -> Lead:
    text = msg.text or {
        MessageType.image: "[фото]",
        MessageType.audio: "[голосовое]",
        MessageType.document: "[документ]",
    }.get(msg.type, "[сообщение]")
    kwargs = {"created_at": at} if at else {}
    return Lead(channel=Channel.whatsapp, client_phone=msg.from_phone, client_name=msg.from_name, text=text, **kwargs)


def looks_like_payment(msg: IncomingMessage) -> bool:
    """Грубая эвристика для чата-кассы: фото чека или текст с суммой и
    платёжным словом. Окончательно это должен подтверждать менеджер —
    см. deals.add_payment, сюда это только помечает, что стоит показать ему первым."""
    t = (msg.text or "").lower()
    has_amount = any(ch.isdigit() for ch in t)
    return (msg.type == MessageType.image and has_amount) or (
        msg.type == MessageType.text and has_amount and any(w in t for w in PAYMENT_WORDS)
    )


def route_message(msg: IncomingMessage, router: LeadRouter, at: datetime | None = None) -> Lead:
    lead = lead_from_message(msg, at)
    return router.assign(lead)
