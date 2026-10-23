"""Запуск бота: python -m carval.bot.main"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from ..catalog import load_catalog
from ..llm import LLM
from ..settings import get_settings
from ..storage import make_storage
from .handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN в .env")
    if not settings.anthropic_api_key:
        raise SystemExit("Не задан ANTHROPIC_API_KEY в .env")

    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Эти объекты aiogram передаёт в обработчики по имени параметра
    dp = Dispatcher(
        catalog=load_catalog(settings),
        repo=make_storage(settings),
        llm=LLM(settings.anthropic_api_key),
        settings=settings,
    )
    dp.include_router(router)
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
