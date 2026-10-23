"""Голос: распознавание голосовых сообщений мастера и озвучка ответов бота.

Claude не принимает аудио, поэтому речь распознаёт и озвучивает Yandex SpeechKit:
он хорошо понимает русский и казахский (lang=kk-KK). Голосовое из Telegram
приходит в OGG Opus — SpeechKit принимает его без перекодирования.

Без ключа (YANDEX_API_KEY) голос выключен: бот работает текстом, как раньше.
Проверить на ключах заказчика перед пилотом: endpoint'ы и голоса могут меняться.
"""

from __future__ import annotations

import httpx

from .settings import Settings

STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
MAX_STT_BYTES = 1_000_000  # синхронное распознавание: до ~30 секунд и 1 МБ
MAX_TTS_CHARS = 4500


class VoiceError(RuntimeError):
    pass


class Voice:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.key = settings.yandex_api_key
        self.folder = settings.yandex_folder_id
        self.lang = settings.voice_lang
        self.voice = settings.voice_name
        self.client = client or httpx.AsyncClient(timeout=30)

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Api-Key {self.key}"}

    async def transcribe(self, ogg: bytes) -> str:
        if not self.enabled:
            raise VoiceError("Голос не настроен (нет YANDEX_API_KEY)")
        if len(ogg) > MAX_STT_BYTES:
            raise VoiceError("Голосовое слишком длинное — до 30 секунд")
        params = {"lang": self.lang, "format": "oggopus"}
        if self.folder:
            params["folderId"] = self.folder
        r = await self.client.post(STT_URL, params=params, headers=self._headers(), content=ogg)
        if r.status_code != 200:
            raise VoiceError(f"Распознавание не удалось ({r.status_code})")
        return r.json().get("result", "").strip()

    async def speak(self, text: str) -> bytes:
        """Текст → OGG Opus для отправки голосовым в Telegram."""
        if not self.enabled:
            raise VoiceError("Голос не настроен (нет YANDEX_API_KEY)")
        data = {"text": text[:MAX_TTS_CHARS], "lang": self.lang, "voice": self.voice, "format": "oggopus"}
        if self.folder:
            data["folderId"] = self.folder
        r = await self.client.post(TTS_URL, headers=self._headers(), data=data)
        if r.status_code != 200:
            raise VoiceError(f"Озвучка не удалась ({r.status_code})")
        return r.content


def spoken_summary(report) -> str:
    """Короткая сводка отчёта для озвучки: без таблиц и HTML."""
    car = report.car
    active = report.active_defects
    parts = [f"{car.make} {car.model}, {car.year} год."]
    parts.append(f"Найдено повреждений: {len(active)}." if active else "Повреждений не найдено.")
    st = report.settlement
    if st:
        new = len(st.new_defect_ids)
        parts.append(f"Новых с момента выдачи: {new}." if new else "Новых повреждений нет.")
        parts.append(f"К удержанию {st.total:,} тенге.".replace(",", " "))
        if st.due:
            parts.append(f"Доплата сверх депозита {st.due:,} тенге.".replace(",", " "))
    elif report.estimate:
        e = report.estimate
        parts.append(f"Предложение от {e.offer_low // 1000} до {e.offer_high // 1000} тысяч тенге.")
    if report.needs_manual_review:
        parts.append("Нужна ручная проверка.")
    if report.not_assessable:
        parts.append("Проверьте инструментом: " + "; ".join(report.not_assessable[:2]) + ".")
    return " ".join(parts)
