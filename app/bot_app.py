import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import admin, user
from app.core.config import get_settings
from app.core.logging import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await dp.start_polling(bot, polling_timeout=settings.bot_polling_timeout)


if __name__ == '__main__':
    asyncio.run(main())
