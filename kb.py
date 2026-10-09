"""Клавиатуры для панели управления шефа в Telegram."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def boss_main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню панели управления шефа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Отчет за 7 дней", callback_data="rep:days:7")
    builder.button(text="🗓 Отчет за 30 дней", callback_data="rep:days:30")
    builder.button(text="⚡ Отчет за сегодня", callback_data="rep:days:1")
    builder.button(text="📁 За всё время", callback_data="rep:days:all")
    builder.button(text="📑 Выгрузить Excel (.xlsx)", callback_data="rep:excel:7")
    builder.button(text="👥 Список менеджеров", callback_data="mgr:list")
    builder.button(text="⚙️ Настройки расписания", callback_data="cfg:schedule")
    builder.button(text="🔄 Обновить", callback_data="menu:refresh")
    builder.adjust(2, 2, 1, 2, 1)
    return builder.as_markup()

def report_actions_kb(days: str) -> InlineKeyboardMarkup:
    """Кнопки под готовым отчетом."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📑 Скачать в Excel (.xlsx)", callback_data=f"rep:excel:{days}")
    builder.button(text="🔄 Обновить отчет", callback_data=f"rep:days:{days}")
    builder.button(text="◀️ Главное меню", callback_data="menu:main")
    builder.adjust(1, 1, 1)
    return builder.as_markup()

def managers_menu_kb(managers: list) -> InlineKeyboardMarkup:
    """Клавиатура управления менеджерами."""
    builder = InlineKeyboardBuilder()
    for m in managers:
        builder.button(
            text=f"❌ Удалить: {m['name']}",
            callback_data=f"mgr:del:{m['user_id']}"
        )
    builder.button(text="➕ Как добавить менеджера", callback_data="mgr:help_add")
    builder.button(text="◀️ Назад в меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()

def schedule_settings_kb(weekly_enabled: bool, monthly_enabled: bool) -> InlineKeyboardMarkup:
    """Настройка автоматических отчетов."""
    builder = InlineKeyboardBuilder()
    w_icon = "✅" if weekly_enabled else "❌"
    m_icon = "✅" if monthly_enabled else "❌"
    builder.button(text=f"{w_icon} Еженедельный (Пн 09:00)", callback_data="cfg:toggle_weekly")
    builder.button(text=f"{m_icon} Ежемесячный (1-е число)", callback_data="cfg:toggle_monthly")
    builder.button(text="◀️ Назад в меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()
