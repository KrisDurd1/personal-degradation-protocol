"""Точка входа. Long polling — белый IP и вебхуки не нужны."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from .config import settings
from .handlers import router
from .llm import llm
from .memory import memory
from .tracking import TrackingMiddleware

COMMANDS = [
    BotCommand(command="note", description="записать в журнал"),
    BotCommand(command="journal", description="показать журнал"),
    BotCommand(command="find", description="искать по журналу"),
    BotCommand(command="spravka", description="справка за неделю картинкой"),
    BotCommand(command="pulse", description="краш-тест дня"),
    BotCommand(command="fork", description="развилка: две ветки и цена каждой"),
    BotCommand(command="seal", description="запечатать ветку"),
    BotCommand(command="audit", description="недельный аудит"),
    BotCommand(command="voice", description="сменить голос"),
    BotCommand(command="wipe", description="стереть всё"),
]


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()
    dp.message.outer_middleware(TrackingMiddleware())
    dp.include_router(router)

    await memory.open()
    await bot.set_my_commands(COMMANDS)
    try:
        await dp.start_polling(bot)
    finally:
        await memory.close()
        await llm.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
