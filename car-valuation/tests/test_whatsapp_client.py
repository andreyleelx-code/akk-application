import httpx
import pytest

from carval.settings import Settings
from carval.whatsapp.client import WhatsAppClient, WhatsAppError


def settings(**kw):
    return Settings(whatsapp_access_token="token-123", whatsapp_phone_number_id="999", **kw)


def fake_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_disabled_without_credentials():
    c = WhatsAppClient(Settings())
    assert not c.enabled


async def test_send_text_builds_correct_request():
    import json
    seen = {}
    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    c = WhatsAppClient(settings(), client=fake_client(handler))
    r = await c.send_text("77011112233", "Здравствуйте!")
    assert r["messages"][0]["id"] == "wamid.1"
    assert seen["url"].endswith("/999/messages")
    assert seen["auth"] == "Bearer token-123"
    assert seen["body"]["to"] == "77011112233"
    assert seen["body"]["type"] == "text"
    assert seen["body"]["text"]["body"] == "Здравствуйте!"


async def test_send_without_credentials_raises():
    c = WhatsAppClient(Settings())
    with pytest.raises(WhatsAppError, match="не настроен"):
        await c.send_text("77011112233", "привет")


async def test_api_error_is_readable():
    def handler(request: httpx.Request):
        return httpx.Response(401, json={"error": {"message": "Invalid OAuth access token"}})

    c = WhatsAppClient(settings(), client=fake_client(handler))
    with pytest.raises(WhatsAppError, match="Invalid OAuth access token"):
        await c.send_text("77011112233", "привет")


async def test_send_template_with_params():
    import json
    seen = {}
    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.2"}]})

    c = WhatsAppClient(settings(), client=fake_client(handler))
    await c.send_template("77011112233", "deposit_reminder", params=["57 000 ₸", "25 октября"])
    body = seen["body"]
    assert body["type"] == "template"
    assert body["template"]["name"] == "deposit_reminder"
    assert body["template"]["components"][0]["parameters"][0]["text"] == "57 000 ₸"
