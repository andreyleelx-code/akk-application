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


def image_block(data: bytes, media_type: str | None = None) -> dict:
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
