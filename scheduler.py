"""Планировщик автоматической рассылки отчетов шефу по расписанию."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile

import db
import config
from analyzer import compute_analytics
from reporter import generate_telegram_text, generate_excel_file

log = logging.getLogger("scheduler")

async def send_scheduled_report(bot: Bot, days: int, title: str) -> None:
    """Генерация и отправка планового отчета шефу и админам."""
    log.info("Starting scheduled report generation: %s", title)
    try:
        now = datetime.now()
        start = now - timedelta(days=days)
        start_iso = start.isoformat()
        end_iso = now.isoformat()

        messages = await db.fetch_messages_for_period(start_iso, end_iso)
        responses = await db.fetch_response_times_for_period(start_iso, end_iso)
        events = await db.fetch_events_for_period(start_iso, end_iso)

        stats = compute_analytics(messages, responses, events, title)
        report_text = generate_telegram_text(stats)

        excel_filename = f"report_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
        excel_path = str(config.BASE_DIR / "reports" / excel_filename)
        generate_excel_file(stats, excel_path)

        boss_id = await db.get_boss_id()
        db_admins = [a["user_id"] for a in await db.get_all_admins()]
        recipients = list(set([boss_id] + config.ADMIN_IDS + db_admins))
        for recipient_id in recipients:
            try:
                await bot.send_message(
                    chat_id=recipient_id,
                    text=f"🔔 <b>ПЛАНОВЫЙ АВТОМАТИЧЕСКИЙ ОТЧЕТ</b>\n\n{report_text}",
                    parse_mode="HTML"
                )
                excel_doc = FSInputFile(excel_path, filename=f"Отчет_Шефу_{now.strftime('%d_%m_%Y')}.xlsx")
                await bot.send_document(
                    chat_id=recipient_id,
                    document=excel_doc,
                    caption="📑 Полная таблица с аналитикой и логами в Excel"
                )
                log.info("Scheduled report sent successfully to user %s", recipient_id)
            except Exception as e:
                log.error("Failed to send scheduled report to %s: %s", recipient_id, e)

    except Exception as exc:
        log.exception("Error in send_scheduled_report: %s", exc)


async def scheduler_loop(bot: Bot):
    """
    Фоновый цикл проверки наступления времени отчетов.
    Проверяет раз в 60 секунд наступление заданного дня и часа.
    """
    last_weekly_sent_date: Optional[str] = None
    last_monthly_sent_date: Optional[str] = None

    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 1. Еженедельный отчет: каждый понедельник (weekday=0) в 09:00
            if (
                config.WEEKLY_REPORT_ENABLED
                and now.weekday() == config.WEEKLY_REPORT_DAY
                and now.hour == config.REPORT_HOUR
                and now.minute == config.REPORT_MINUTE
                and last_weekly_sent_date != today_str
            ):
                last_weekly_sent_date = today_str
                await send_scheduled_report(bot, days=7, title="Еженедельный отчет (последние 7 дней)")

            # 2. Ежемесячный отчет: 1-е число каждого месяца в 09:00
            if (
                config.MONTHLY_REPORT_ENABLED
                and now.day == 1
                and now.hour == config.REPORT_HOUR
                and now.minute == config.REPORT_MINUTE
                and last_monthly_sent_date != today_str
            ):
                last_monthly_sent_date = today_str
                await send_scheduled_report(bot, days=30, title="Ежемесячный отчет (последние 30 дней)")

        except Exception as e:
            log.error("Scheduler loop error: %s", e)

        await asyncio.sleep(45)
