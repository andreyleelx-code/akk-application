"""Отправка сообщений через WhatsApp Business (Meta Cloud API).

API: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
Без WHATSAPP_ACCESS_TOKEN клиент выключен — удобно разрабатывать остальное
(роутинг лидов, агент) без живого номера.
"""

from __future__ import annotations

import httpx

from ..settings import Settings

GRAPH_VERSION = "v21.0"


class WhatsAppError(RuntimeError):
    pass


class WhatsAppClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.token = settings.whatsapp_access_token
        self.phone_id = settings.whatsapp_phone_number_id
        self.client = client or httpx.AsyncClient(timeout=30)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.phone_id)

    @property
    def _url(self) -> str:
        return f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_id}/messages"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def _send(self, payload: dict) -> dict:
        if not self.enabled:
            raise WhatsAppError("WhatsApp не настроен (нет WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID)")
        payload = {"messaging_product": "whatsapp", **payload}
        try:
            r = await self.client.post(self._url, headers=self._headers(), json=payload)
        except httpx.ConnectError as e:
            raise WhatsAppError("Нет связи с WhatsApp API") from e
        if r.status_code >= 400:
            detail = r.json().get("error", {}).get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
            raise WhatsAppError(f"WhatsApp API вернул ошибку {r.status_code}: {detail}")
        return r.json()

    async def send_text(self, to: str, text: str, *, preview_url: bool = False) -> dict:
        """to — номер клиента в формате E.164 без '+', например '77011112233'."""
        return await self._send({
            "to": to, "type": "text",
            "text": {"body": text[:4096], "preview_url": preview_url},
        })

    async def send_template(self, to: str, template_name: str, lang: str = "ru", params: list[str] | None = None) -> dict:
        """Шаблонные сообщения (напоминание о возврате, акт и т.п.) — единственный способ
        написать клиенту первым вне 24-часового окна с его последнего сообщения.
        Шаблон должен быть заранее одобрен в Meta Business Manager."""
        payload: dict = {"to": to, "type": "template",
                          "template": {"name": template_name, "language": {"code": lang}}}
        if params:
            payload["template"]["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        return await self._send(payload)

    async def mark_read(self, message_id: str) -> dict:
        return await self._send({"status": "read", "message_id": message_id})

    async def media_url(self, media_id: str) -> str:
        if not self.enabled:
            raise WhatsAppError("WhatsApp не настроен")
        r = await self.client.get(f"https://graph.facebook.com/{GRAPH_VERSION}/{media_id}",
                                   headers={"Authorization": f"Bearer {self.token}"})
        if r.status_code >= 400:
            raise WhatsAppError(f"Не удалось получить ссылку на файл ({r.status_code})")
        return r.json()["url"]

    async def download_media(self, media_id: str) -> bytes:
        """Фото или голосовое из входящего сообщения: сначала URL, потом сам файл —
        так устроен Graph API, в одно обращение файл не отдаётся."""
        url = await self.media_url(media_id)
        r = await self.client.get(url, headers={"Authorization": f"Bearer {self.token}"})
        if r.status_code >= 400:
            raise WhatsAppError(f"Не удалось скачать файл ({r.status_code})")
        return r.content
