"""Автоматический генератор отчетов для шефа — точка входа."""
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, PORT
from db import init_db
from handlers import router as reporter_router
from scheduler import scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("boss_reporter")


async def health_check(_request):
    return web.Response(text="Boss Reporter Bot OK")


async def start_health_server():
    """Мини-сервер для health-check (нужен для деплоя на Render/Koyeb)."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        log.info("Health server running on port %s", PORT)
    except Exception as e:
        log.warning("Health server port %s busy (%s), skipping web", PORT, e)
    return runner


async def on_startup(bot: Bot):
    await init_db()
    log.info("Database initialized")

    # Установка подсказок команд в Telegram
    try:
        await bot.set_my_commands([
            BotCommand(command="menu", description="📊 Панель отчетов шефа"),
            BotCommand(command="report", description="📈 Сформировать отчет"),
            BotCommand(command="admins", description="👑 Администраторы и Шеф"),
            BotCommand(command="managers", description="👥 Список менеджеров"),
            BotCommand(command="settings", description="⚙️ Настройки расписания"),
            BotCommand(command="help", description="❓ Инструкция по работе"),
        ])
    except Exception as e:
        log.warning("Could not set bot commands: %s", e)

    # Запуск фонового планировщика отчетов (еженедельно/ежемесячно)
    asyncio.create_task(scheduler_loop(bot))
    log.info("Scheduler task started")


async def main():
    if not BOT_TOKEN:
        raise SystemExit("ОШИБКА: BOT_TOKEN не указан в .env файле!")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(reporter_router)
    dp.startup.register(on_startup)

    web_runner = await start_health_server()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Starting bot polling for @Statictipbot...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if web_runner:
            await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

