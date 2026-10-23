"""Обёртка над Claude API: фото + промпт → проверенный pydantic-объект."""

from __future__ import annotations

import base64
from typing import TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def sniff_media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


MAX_SIDE = 1568  # больше Claude всё равно уменьшит; лишние пиксели — лишние деньги
MAX_BYTES = 3_500_000  # лимит API на картинку — 5 МБ (с запасом на base64)


def prepare_image(data: bytes) -> bytes:
    """Фото «файлом» с телефона бывает 12 Мп и 6 МБ: уменьшаем и поворачиваем по EXIF."""
    from io import BytesIO

    from PIL import Image, ImageOps

    try:
        img = Image.open(BytesIO(data))
    except Exception:
        return data
    if max(img.size) <= MAX_SIDE and len(data) <= MAX_BYTES and not img.getexif().get(0x0112):
        return data
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def image_block(data: bytes, media_type: str | None = None) -> dict:
    prepared = prepare_image(data)
    if prepared is not data:
        data, media_type = prepared, "image/jpeg"
    media_type = media_type or sniff_media_type(data)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


class LLM:
    def __init__(self, api_key: str | None = None, client: anthropic.AsyncAnthropic | None = None):
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key or None)

    async def parse(
        self,
        *,
        model: str,
        system: str,
        content: list[dict],
        schema: type[T],
        effort: str = "medium",
        max_tokens: int = 16000,
    ) -> T:
        try:
            resp = await self.client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": effort},
            )
        except anthropic.RateLimitError as e:
            raise LLMError("Превышен лимит запросов к Claude, повторите позже") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API вернул ошибку {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Нет связи с Claude API") from e

        if resp.stop_reason == "refusal":
            raise LLMError("Модель отказалась обрабатывать запрос")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise LLMError("Ответ модели обрезан или не прошёл проверку схемы")
        return resp.parsed_output


    async def search(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        city: str = "Almaty",
        country: str = "KZ",
        max_uses: int = 6,
        max_continuations: int = 3,
    ) -> tuple[str, list[str]]:
        """Запрос с веб-поиском Claude. Возвращает (текст ответа, адреса найденных страниц).

        Проверенный формат ответа несовместим с цитатами, которые даёт поиск,
        поэтому разбор в таблицу делается вторым запросом (parse).
        """
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": max_uses,
            "user_location": {"type": "approximate", "city": city, "country": country},
        }]
        messages: list[dict] = [{"role": "user", "content": prompt}]
        try:
            resp = await self.client.messages.create(
                model=model, max_tokens=16000, system=system, messages=messages, tools=tools,
                output_config={"effort": "medium"},
            )
            blocks = list(resp.content)
            for _ in range(max_continuations):
                if resp.stop_reason != "pause_turn":
                    break
                # сервер продолжит поиск с того места, где остановился
                messages = [messages[0], {"role": "assistant", "content": blocks}]
                resp = await self.client.messages.create(
                    model=model, max_tokens=16000, system=system, messages=messages, tools=tools,
                    output_config={"effort": "medium"},
                )
                blocks.extend(resp.content)
        except anthropic.RateLimitError as e:
            raise LLMError("Превышен лимит запросов к Claude, повторите позже") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API вернул ошибку {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Нет связи с Claude API") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Модель отказалась обрабатывать запрос")

        text, urls = [], []
        for block in blocks:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                urls.extend(r.url for r in block.content if getattr(r, "url", None))
        return "\n".join(text), urls
