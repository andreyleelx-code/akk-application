from datetime import datetime, timezone

from carval.leads import LeadRouter
from carval.whatsapp.router import looks_like_payment, route_message
from carval.whatsapp.webhook import IncomingMessage, MessageType


def msg(phone="77011112233", text="Добрый день", mtype=MessageType.text, media_id=None):
    return IncomingMessage(wa_message_id="w1", from_phone=phone, from_name="Клиент",
                            type=mtype, text=text, media_id=media_id)


def test_route_message_assigns_manager_like_leads_py():
    r = LeadRouter(["Ерлан", "Дана"])
    day = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)
    lead = route_message(msg(), r, at=day)
    assert lead.assigned_to == "Ерлан"
    assert not lead.handled_by_agent


def test_route_message_after_hours_flags_agent():
    r = LeadRouter(["Ерлан", "Дана"])
    night = datetime(2026, 10, 24, 23, tzinfo=timezone.utc)
    lead = route_message(msg(), r, at=night)
    assert lead.handled_by_agent


def test_returning_client_same_manager_through_whatsapp():
    r = LeadRouter(["Ерлан", "Дана"])
    day = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)
    first = route_message(msg(phone="77099998877"), r, at=day)
    route_message(msg(phone="77011112233"), r, at=day)  # другой клиент, сдвигает очередь
    second = route_message(msg(phone="77099998877", text="снова я"), r, at=day)
    assert second.assigned_to == first.assigned_to


def test_image_without_amount_is_not_a_payment():
    assert not looks_like_payment(msg(mtype=MessageType.image, text="вот машина", media_id="m1"))


def test_image_with_amount_looks_like_payment():
    assert looks_like_payment(msg(mtype=MessageType.image, text="оплатил 50000", media_id="m1"))


def test_text_with_amount_and_keyword_looks_like_payment():
    assert looks_like_payment(msg(text="перевёл 30000 на kaspi"))


def test_text_with_amount_but_no_keyword_is_not_flagged():
    assert not looks_like_payment(msg(text="буду в 18:00"))
