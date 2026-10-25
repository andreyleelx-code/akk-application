import hashlib
import hmac
import json

from carval.whatsapp.webhook import MessageType, parse_webhook, verify_signature

SECRET = "app-secret-xyz"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_correct_one():
    body = b'{"a":1}'
    assert verify_signature(SECRET, body, sign(body))


def test_verify_signature_rejects_wrong_or_missing():
    body = b'{"a":1}'
    assert not verify_signature(SECRET, body, "sha256=deadbeef")
    assert not verify_signature(SECRET, body, None)
    assert not verify_signature("", body, sign(body))  # секрет не настроен — всегда отказ
    assert not verify_signature(SECRET, body, "not-prefixed")


TEXT_PAYLOAD = {
    "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "77011112233", "profile": {"name": "Арман"}}],
        "messages": [{"id": "wamid.A", "from": "77011112233", "timestamp": "1700000000",
                      "type": "text", "text": {"body": "Нужна машина на выходные"}}],
    }}]}]
}

IMAGE_PAYLOAD = {
    "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "77022223344", "profile": {"name": "Дана"}}],
        "messages": [{"id": "wamid.B", "from": "77022223344", "timestamp": "1700000001",
                      "type": "image", "image": {"id": "media-1", "caption": "оплатил депозит"}}],
    }}]}]
}

STATUS_ONLY_PAYLOAD = {
    "entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.A", "status": "delivered"}]}}]}]
}


def test_parse_text_message():
    msgs = parse_webhook(TEXT_PAYLOAD)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.wa_message_id == "wamid.A"
    assert m.from_phone == "77011112233"
    assert m.from_name == "Арман"
    assert m.type == MessageType.text
    assert m.text == "Нужна машина на выходные"
    assert m.media_id is None


def test_parse_image_message_keeps_caption_and_media_id():
    msgs = parse_webhook(IMAGE_PAYLOAD)
    m = msgs[0]
    assert m.type == MessageType.image
    assert m.media_id == "media-1"
    assert m.text == "оплатил депозит"


def test_status_only_payload_yields_no_messages():
    assert parse_webhook(STATUS_ONLY_PAYLOAD) == []


def test_parse_is_json_roundtrip_safe():
    # ровно то, что реально приходит на вебхук: байты -> json -> parse
    body = json.dumps(TEXT_PAYLOAD).encode()
    assert parse_webhook(json.loads(body))[0].from_phone == "77011112233"
