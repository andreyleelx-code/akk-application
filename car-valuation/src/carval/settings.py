"""Настройки из переменных окружения (.env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    telegram_bot_token: str = ""
    senior_appraiser_ids: str = ""

    anthropic_api_key: str = ""
    model_main: str = Field("claude-opus-5-5", alias="CARVAL_MODEL_MAIN")
    model_fast: str = Field("claude-haiku-5-5", alias="CARVAL_MODEL_FAST")

    storage: Literal["local", "supabase"] = Field("local", alias="CARVAL_STORAGE")
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "car-photos"

    currency: str = Field("KZT", alias="CARVAL_CURRENCY")
    parts_web_search: bool = Field(True, alias="CARVAL_PARTS_WEB_SEARCH")
    city: str = Field("Алматы", alias="CARVAL_CITY")

    # Голос (Yandex SpeechKit). Пусто — голос выключен.
    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    voice_lang: str = Field("ru-RU", alias="CARVAL_VOICE_LANG")  # kk-KK — казахский
    voice_name: str = Field("alena", alias="CARVAL_VOICE_NAME")
    voice_replies: bool = Field(True, alias="CARVAL_VOICE_REPLIES")

    # WhatsApp (Meta Cloud API). Пусто — вебхук работает, но ничего не отправляет.
    # Получаются в business.facebook.com после регистрации номера — см. docs/09-whatsapp-setup.md
    whatsapp_access_token: str = Field("", alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str = Field("", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_verify_token: str = Field("", alias="WHATSAPP_VERIFY_TOKEN")  # придумываете сами, вписываете при подписке вебхука
    whatsapp_app_secret: str = Field("", alias="WHATSAPP_APP_SECRET")  # для проверки подписи входящих запросов
    whatsapp_work_from: int = Field(9, alias="CARVAL_WHATSAPP_WORK_FROM")
    whatsapp_work_to: int = Field(21, alias="CARVAL_WHATSAPP_WORK_TO")
    whatsapp_managers: str = Field("", alias="CARVAL_WHATSAPP_MANAGERS")  # "Ерлан,Дана,Арман"

    config_dir: Path = PROJECT_ROOT / "config"
    prompts_dir: Path = PROJECT_ROOT / "prompts"
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def senior_ids(self) -> set[int]:
        return {int(x) for x in self.senior_appraiser_ids.split(",") if x.strip()}

    @property
    def manager_list(self) -> list[str]:
        return [x.strip() for x in self.whatsapp_managers.split(",") if x.strip()]

    def config_file(self, name: str) -> Path:
        """Рабочий файл заказчика, если он есть, иначе пример (*.example.*)."""
        real = self.config_dir / name
        if real.exists():
            return real
        stem, _, ext = name.rpartition(".")
        return self.config_dir / f"{stem}.example.{ext}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
