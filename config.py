"""Конфигурация бота-генератора отчетов для шефа."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ID шефа / владельца магазина в Telegram (куда присылать отчеты)
_raw_boss = os.getenv("BOSS_ID", "8653358704")
try:
    BOSS_ID = int(_raw_boss)
except ValueError:
    BOSS_ID = 8653358704

# Список дополнительных администраторов/наблюдателей
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", f"{BOSS_ID}").split(",") if x.strip().isdigit()]
if BOSS_ID not in ADMIN_IDS:
    ADMIN_IDS.append(BOSS_ID)

# Путь к базе данных
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "reporter.db"))

# Порт для веб-сервера / health-check (если деплоить на Render)
PORT = int(os.getenv("PORT", "10002"))

# Настройки расписания автоматических отчетов по умолчанию
WEEKLY_REPORT_ENABLED = os.getenv("WEEKLY_REPORT_ENABLED", "true").lower() in ("true", "1", "yes")
MONTHLY_REPORT_ENABLED = os.getenv("MONTHLY_REPORT_ENABLED", "true").lower() in ("true", "1", "yes")

# День недели для еженедельного отчета (0 = понедельник, 6 = воскресенье)
WEEKLY_REPORT_DAY = int(os.getenv("WEEKLY_REPORT_DAY", "0"))  # Понедельник
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))              # 09:00 утра
REPORT_MINUTE = int(os.getenv("REPORT_MINUTE", "0"))
