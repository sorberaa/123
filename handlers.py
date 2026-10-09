"""Обработчики событий для групп магазина и личной панели шефа."""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile

import db
import config
from categories import classify_text, is_question_message
from analyzer import compute_analytics
from reporter import generate_telegram_text, generate_excel_file
from json_importer import analyze_telegram_export_json
from kb import (
    boss_main_menu_kb,
    report_actions_kb,
    managers_menu_kb,
    schedule_settings_kb,
    admins_panel_kb,
    transfer_boss_confirm_kb
)

log = logging.getLogger("handlers")
router = Router(name="reporter_handlers")


async def check_admin_or_boss(user_id: int) -> bool:
    return await db.is_admin_or_boss(user_id)


# =========================================================================
# 1. ОБРАБОТКА СООБЩЕНИЙ В ГРУППЕ (ЧАТЕ МАГАЗИНА)
# =========================================================================

@router.message(F.chat.type.in_({"group", "supergroup"}), F.new_chat_members)
async def on_new_members(message: Message):
    """Фиксация входа новых участников в чат."""
    chat_id = message.chat.id
    chat_title = message.chat.title or "Чат магазина"
    await db.save_tracked_chat(chat_id, chat_title)

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        uname = member.full_name or member.username or str(member.id)
        now_iso = datetime.now().isoformat()
        await db.record_chat_event(chat_id, "join", member.id, uname, now_iso)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.left_chat_member)
async def on_left_member(message: Message):
    """Фиксация выхода участника из чата."""
    member = message.left_chat_member
    if member and not member.is_bot:
        uname = member.full_name or member.username or str(member.id)
        now_iso = datetime.now().isoformat()
        await db.record_chat_event(message.chat.id, "leave", member.id, uname, now_iso)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("setmanager"))
async def cmd_group_setmanager(message: Message):
    """Назначение менеджера ответом на сообщение в группе."""
    if not await check_admin_or_boss(message.from_user.id):
        return await message.reply("⛔ Назначать менеджеров может только шеф или администратор.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("ℹ️ Ответьте этой командой на сообщение сотрудника: <code>/setmanager</code>")

    name = target.full_name or target.username or f"Менеджер #{target.id}"
    await db.add_manager(target.id, name)
    await message.reply(f"✅ <b>{name}</b> успешно назначен менеджером поддержки! Теперь его скорость ответов будет учитываться в отчете.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("delmanager"))
async def cmd_group_delmanager(message: Message):
    """Снятие менеджера ответом на сообщение в группе."""
    if not await check_admin_or_boss(message.from_user.id):
        return await message.reply("⛔ Доступно только шефу или администратору.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("ℹ️ Ответьте на сообщение менеджера: <code>/delmanager</code>")

    await db.remove_manager(target.id)
    await message.reply(f"❌ Пользователь #{target.id} удален из менеджеров поддержки.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("addadmin"))
async def cmd_group_addadmin(message: Message):
    """Назначение администратора ответом на сообщение в группе."""
    if not await check_admin_or_boss(message.from_user.id):
        return await message.reply("⛔ Назначать администраторов может только шеф.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("ℹ️ Ответьте на сообщение пользователя: <code>/addadmin</code>")

    name = target.full_name or target.username or f"Админ #{target.id}"
    await db.add_admin(target.id, name, added_by=message.from_user.id)
    await message.reply(f"🛡 <b>{name}</b> (ID: <code>{target.id}</code>) назначен Администратором отчетов!\nТеперь он имеет доступ к панели /menu и выгрузке Excel.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("deladmin"))
async def cmd_group_deladmin(message: Message):
    """Снятие администратора ответом на сообщение в группе."""
    if not await db.is_boss(message.from_user.id):
        return await message.reply("⛔ Снимать администраторов может только главный Шеф/Владелец.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("ℹ️ Ответьте на сообщение администратора: <code>/deladmin</code>")

    await db.remove_admin(target.id)
    await message.reply(f"❌ Администратор #{target.id} снят с должности.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("transferboss"))
async def cmd_group_transferboss(message: Message):
    """Передача прав шефа ответом на сообщение в группе."""
    if not await db.is_boss(message.from_user.id):
        return await message.reply("⛔ Передавать права Шефа может только действующий Шеф/Владелец.")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    if not target:
        return await message.reply("ℹ️ Ответьте на сообщение пользователя, которому передаете права: <code>/transferboss</code>")

    name = target.full_name or target.username or f"#{target.id}"
    await db.set_boss_id(target.id)
    await message.reply(f"👑 <b>ПРАВА ШЕФА УСПЕШНО ПЕРЕДАНЫ!</b>\n\nНовый владелец бота: <b>{name}</b> (ID: <code>{target.id}</code>).\nТеперь все автоматические отчеты будут приходить ему.")



@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def on_group_message(message: Message):
    """
    Основной сборщик сообщений из чата магазина:
    - Сохранение сообщений
    - Категоризация вопросов и болей
    - Замер скорости первого ответа менеджера
    """
    chat_id = message.chat.id
    chat_title = message.chat.title or "Чат магазина"
    await db.save_tracked_chat(chat_id, chat_title)

    user = message.from_user
    if not user or user.is_bot:
        return

    text = message.text or ""
    now_dt = datetime.now()
    now_iso = now_dt.isoformat()

    is_mgr = await db.is_manager(user.id)
    cat_key, cat_title = classify_text(text)
    is_q = is_question_message(text)

    reply_to_id = message.reply_to_message.message_id if message.reply_to_message else None

    # Сохраняем сообщение в базу
    await db.save_message(
        message_id=message.message_id,
        chat_id=chat_id,
        chat_title=chat_title,
        user_id=user.id,
        user_name=user.full_name or "Клиент",
        user_handle=user.username or "",
        is_mgr=is_mgr,
        reply_to_msg_id=reply_to_id,
        text=text,
        timestamp=now_iso,
        category=cat_key,
        category_title=cat_title,
        is_question=is_q
    )

    # Если отвечает менеджер на чье-то сообщение в чате
    if is_mgr and reply_to_id:
        parent_msg = await db.get_message(chat_id, reply_to_id)
        if parent_msg and not parent_msg.get("is_manager"):
            try:
                parent_dt = datetime.fromisoformat(parent_msg["timestamp"])
                diff_sec = (now_dt - parent_dt).total_seconds()
                if diff_sec >= 0:
                    await db.record_response_time(
                        chat_id=chat_id,
                        question_msg_id=parent_msg["message_id"],
                        question_time=parent_msg["timestamp"],
                        reply_msg_id=message.message_id,
                        reply_time=now_iso,
                        client_id=parent_msg["user_id"],
                        client_name=parent_msg.get("user_name", "Клиент"),
                        manager_id=user.id,
                        manager_name=user.full_name or "Менеджер",
                        category=parent_msg.get("category_title", "❓ Прочие вопросы"),
                        response_time_seconds=diff_sec
                    )
            except Exception as e:
                log.error("Failed to record response time: %s", e)


# =========================================================================
# 2. ПАНЕЛЬ УПРАВЛЕНИЯ ШЕФА В ЛИЧКЕ БОТА
# =========================================================================

@router.message(F.chat.type == "private", CommandStart())
@router.message(F.chat.type == "private", Command("menu"))
@router.message(F.chat.type == "private", Command("report"))
async def cmd_boss_start(message: Message):
    """Приветствие и главное меню шефа."""
    if not await check_admin_or_boss(message.from_user.id):
        return await message.answer(
            f"👋 Здравствуйте! Это служебный бот-генератор отчетов для владельца магазина.\n\n"
            f"Ваш Telegram ID: <code>{message.from_user.id}</code> (ожидается подтверждение шефа)."
        )

    chats = await db.get_tracked_chats()
    mgrs = await db.get_all_managers()

    welcome_text = (
        f"👔 <b>ПАНЕЛЬ УПРАВЛЕНИЯ ШЕФА</b>\n\n"
        f"Добро пожаловать! Бот собирает аналитику из чатов магазина:\n"
        f"• Количество сообщений и новых участников\n"
        f"• Главные боли и вопросы клиентов (доставка, цены, размеры...)\n"
        f"• Скорость ответов поддержки и эффективность менеджеров\n\n"
        f"📍 <b>Подключенных чатов:</b> {len(chats)}\n"
        f"👥 <b>Менеджеров в учете:</b> {len(mgrs)}\n\n"
        f"Выберите период для формирования отчета ниже 👇\n"
        f"<i>(Или отправьте файл экспорта result.json для мгновенного анализа архива)</i>"
    )
    await message.answer(welcome_text, reply_markup=boss_main_menu_kb())


@router.callback_query(F.data == "menu:main")
@router.callback_query(F.data == "menu:refresh")
async def cb_back_to_menu(cb: CallbackQuery):
    await cb.answer()
    chats = await db.get_tracked_chats()
    mgrs = await db.get_all_managers()
    text = (
        f"👔 <b>ПАНЕЛЬ УПРАВЛЕНИЯ ШЕФА</b>\n\n"
        f"📍 <b>Подключенных чатов:</b> {len(chats)}\n"
        f"👥 <b>Менеджеров в учете:</b> {len(mgrs)}\n\n"
        f"Выберите действие в меню ниже:"
    )
    await cb.message.edit_text(text, reply_markup=boss_main_menu_kb())


@router.callback_query(F.data.startswith("rep:days:"))
async def cb_generate_report(cb: CallbackQuery):
    """Генерация текстового отчета за указанное количество дней."""
    await cb.answer("Формирую отчет...")
    days_arg = cb.data.split(":")[2]

    now = datetime.now()
    if days_arg == "all":
        start_iso = "1970-01-01T00:00:00"
        title = "За всё время сбора данных"
    else:
        d = int(days_arg)
        start_iso = (now - timedelta(days=d)).isoformat()
        if d == 1:
            title = "За сегодня"
        elif d == 7:
            title = "За последние 7 дней (неделя)"
        elif d == 30:
            title = "За последние 30 дней (месяц)"
        else:
            title = f"За {d} дней"

    end_iso = now.isoformat()

    messages = await db.fetch_messages_for_period(start_iso, end_iso)
    responses = await db.fetch_response_times_for_period(start_iso, end_iso)
    events = await db.fetch_events_for_period(start_iso, end_iso)

    stats = compute_analytics(messages, responses, events, title)
    rep_text = generate_telegram_text(stats)

    await cb.message.edit_text(rep_text, reply_markup=report_actions_kb(days_arg))


@router.callback_query(F.data.startswith("rep:excel:"))
async def cb_export_excel(cb: CallbackQuery):
    """Генерация и отправка документа Excel."""
    await cb.answer("Генерирую таблицу Excel...")
    days_arg = cb.data.split(":")[2]

    now = datetime.now()
    if days_arg == "all":
        start_iso = "1970-01-01T00:00:00"
        title = "Все время"
    else:
        d = int(days_arg)
        start_iso = (now - timedelta(days=d)).isoformat()
        title = f"{d} дней"

    end_iso = now.isoformat()

    messages = await db.fetch_messages_for_period(start_iso, end_iso)
    responses = await db.fetch_response_times_for_period(start_iso, end_iso)
    events = await db.fetch_events_for_period(start_iso, end_iso)

    stats = compute_analytics(messages, responses, events, f"Отчет за {title}")

    reports_dir = config.BASE_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report_boss_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = str(reports_dir / filename)

    generate_excel_file(stats, filepath)

    excel_doc = FSInputFile(filepath, filename=f"Отчет_Шефу_{now.strftime('%d_%m_%Y')}.xlsx")
    await cb.message.answer_document(
        document=excel_doc,
        caption=f"📑 <b>Excel-отчет для шефа</b> ({title})\nВключает сводку KPI, показатели менеджеров и детальный лог."
    )


@router.callback_query(F.data == "mgr:list")
async def cb_managers_list(cb: CallbackQuery):
    """Просмотр списка менеджеров."""
    await cb.answer()
    managers = await db.get_all_managers()
    text = (
        f"👥 <b>СПИСОК МЕНЕДЖЕРОВ ПОДДЕРЖКИ:</b>\n\n"
        f"Менеджеры определяют, чьи ответы клиентам учитываются в расчете скорости (First Response Time).\n\n"
    )
    if not managers:
        text += "<i>Пока нет зарегистрированных менеджеров.</i>\n\n"
    else:
        for idx, m in enumerate(managers, 1):
            text += f"{idx}. <b>{m['name']}</b> (ID: <code>{m['user_id']}</code>)\n"
        text += "\n<i>Нажмите на кнопку ниже, чтобы удалить менеджера:</i>"

    await cb.message.edit_text(text, reply_markup=managers_menu_kb(managers))


@router.callback_query(F.data.startswith("mgr:del:"))
async def cb_manager_delete(cb: CallbackQuery):
    mid = int(cb.data.split(":")[2])
    await db.remove_manager(mid)
    await cb.answer("Менеджер удален")
    managers = await db.get_all_managers()
    await cb.message.edit_text("✅ Менеджер удален из системы.", reply_markup=managers_menu_kb(managers))


@router.callback_query(F.data == "mgr:help_add")
async def cb_manager_help_add(cb: CallbackQuery):
    await cb.answer()
    text = (
        "➕ <b>КАК ДОБАВИТЬ МЕНЕДЖЕРА:</b>\n\n"
        "<b>Способ 1 (самый удобный):</b>\n"
        "В чате магазина ответьте (Reply) на любое сообщение сотрудника командой:\n"
        "<code>/setmanager</code>\n\n"
        "<b>Способ 2 (через личные сообщения):</b>\n"
        "Отправьте боту команду с Telegram ID и именем:\n"
        "<code>/addmanager 123456789 Иван Менеджер</code>\n"
    )
    await cb.message.answer(text)


@router.message(F.chat.type == "private", Command("addmanager"))
async def cmd_add_manager_pm(message: Message):
    """Ручное добавление менеджера через команду в ЛС."""
    if not await check_admin_or_boss(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        return await message.answer("Формат: <code>/addmanager &lt;ID&gt; &lt;Имя&gt;</code>\nПример: <code>/addmanager 123456789 Иван</code>")

    mid = int(parts[1])
    name = parts[2].strip()
    await db.add_manager(mid, name)
    await message.answer(f"✅ Менеджер <b>{name}</b> (ID <code>{mid}</code>) успешно добавлен в базу!")


# =========================================================================
# УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ И ШЕФОМ В ЛС
# =========================================================================

@router.callback_query(F.data == "adm:panel")
async def cb_admin_panel(cb: CallbackQuery):
    """Панель управления доступом: текущий шеф и список админов."""
    await cb.answer()
    user_id = cb.from_user.id
    if not await check_admin_or_boss(user_id):
        return await cb.message.answer("⛔ Доступ ограничен.")

    boss_id = await db.get_boss_id()
    is_boss_user = (user_id == boss_id)
    admins = await db.get_all_admins()

    text = (
        f"👑 <b>УПРАВЛЕНИЕ ПРАВАМИ И ДОСТУПОМ</b>\n\n"
        f"👑 <b>Главный Шеф (Владелец):</b> <code>{boss_id}</code>\n\n"
        f"🛡 <b>Администраторы отчетов ({len(admins)}):</b>\n"
    )
    if not admins:
        text += "<i>Назначенных администраторов пока нет.</i>\n"
    else:
        for idx, a in enumerate(admins, 1):
            text += f"{idx}. <b>{a['name']}</b> (ID: <code>{a['user_id']}</code>)\n"

    text += (
        f"\n<i>Администраторы имеют полный доступ к отчетам и Excel. "
        f"Только Шеф может передавать права владельца и удалять админов.</i>"
    )
    await cb.message.edit_text(text, reply_markup=admins_panel_kb(is_boss_user, admins))


@router.callback_query(F.data.startswith("adm:del:"))
async def cb_admin_del(cb: CallbackQuery):
    """Удаление администратора шефом."""
    user_id = cb.from_user.id
    if not await db.is_boss(user_id):
        return await cb.answer("⛔ Только главный Шеф может снимать администраторов!", show_alert=True)

    target_id = int(cb.data.split(":")[2])
    await db.remove_admin(target_id)
    await cb.answer("Администратор снят")
    await cb_admin_panel(cb)


@router.callback_query(F.data == "adm:help_add")
async def cb_admin_help_add(cb: CallbackQuery):
    await cb.answer()
    text = (
        "➕ <b>КАК НАЗНАЧИТЬ АДМИНИСТРАТОРА:</b>\n\n"
        "<b>Способ 1:</b> В чате магазина ответьте (Reply) на сообщение человека командой:\n"
        "<code>/addadmin</code>\n\n"
        "<b>Способ 2:</b> В этом чате отправьте ID и имя:\n"
        "<code>/addadmin 123456789 Алексей</code>\n"
    )
    await cb.message.answer(text)


@router.callback_query(F.data == "adm:help_transfer")
async def cb_admin_help_transfer(cb: CallbackQuery):
    await cb.answer()
    text = (
        "👑 <b>КАК ПЕРЕДАТЬ ПРАВА ШЕФА (ВЛАДЕЛЬЦА):</b>\n\n"
        "<b>Способ 1 (в группе):</b> Ответьте на сообщение человека командой:\n"
        "<code>/transferboss</code>\n\n"
        "<b>Способ 2 (в личке):</b> Отправьте команду с его ID:\n"
        "<code>/transferboss 123456789</code>\n\n"
        "⚠️ <i>После передачи все автоматические отчеты будут приходить новому владельцу.</i>"
    )
    await cb.message.answer(text)


@router.message(F.chat.type == "private", Command("addadmin"))
async def cmd_addadmin_pm(message: Message):
    """Назначение администратора через команду в ЛС."""
    if not await check_admin_or_boss(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("Формат: <code>/addadmin &lt;Telegram_ID&gt; [Имя]</code>\nПример: <code>/addadmin 123456789 Алексей</code>")

    target_id = int(parts[1])
    name = parts[2].strip() if len(parts) > 2 else f"Админ #{target_id}"
    await db.add_admin(target_id, name, added_by=message.from_user.id)
    await message.answer(f"🛡 <b>{name}</b> (ID: <code>{target_id}</code>) успешно назначен Администратором!")


@router.message(F.chat.type == "private", Command("deladmin"))
async def cmd_deladmin_pm(message: Message):
    """Снятие администратора через команду в ЛС."""
    if not await db.is_boss(message.from_user.id):
        return await message.answer("⛔ Снимать администраторов может только главный Шеф!")

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("Формат: <code>/deladmin &lt;Telegram_ID&gt;</code>")

    target_id = int(parts[1])
    await db.remove_admin(target_id)
    await message.answer(f"❌ Администратор ID <code>{target_id}</code> снят с должности.")


@router.message(F.chat.type == "private", Command("transferboss"))
async def cmd_transferboss_pm(message: Message):
    """Передача прав шефа через команду в ЛС с подтверждением."""
    if not await db.is_boss(message.from_user.id):
        return await message.answer("⛔ Передавать права может только действующий Шеф/Владелец!")

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.answer("Формат: <code>/transferboss &lt;Telegram_ID&gt;</code>\nПример: <code>/transferboss 987654321</code>")

    new_boss_id = int(parts[1])
    if new_boss_id == message.from_user.id:
        return await message.answer("Вы уже являетесь шефом.")

    await message.answer(
        f"⚠️ <b>ВЫ УВЕРЕНЫ, ЧТО ХОТИТЕ ПЕРЕДАТЬ ПРАВА ШЕФА?</b>\n\n"
        f"Новый владелец получит ID: <code>{new_boss_id}</code>.\n"
        f"Все еженедельные и ежемесячные отчеты начнут приходить ему.",
        reply_markup=transfer_boss_confirm_kb(new_boss_id)
    )


@router.callback_query(F.data.startswith("boss:do_transfer:"))
async def cb_boss_do_transfer(cb: CallbackQuery):
    """Выполнение передачи прав шефа."""
    if not await db.is_boss(cb.from_user.id):
        return await cb.answer("⛔ Вы не являетесь текущим шефом!", show_alert=True)

    new_boss_id = int(cb.data.split(":")[2])
    await db.set_boss_id(new_boss_id)
    await cb.answer("Права шефа успешно переданы!", show_alert=True)
    await cb.message.edit_text(
        f"👑 <b>ПРАВА ШЕФА УСПЕШНО ПЕРЕДАНЫ!</b>\n\n"
        f"Новый Шеф/Владелец: <code>{new_boss_id}</code>.\n"
        f"Теперь он является главным получателем отчетов и администратором бота."
    )


@router.message(F.chat.type == "private", Command("admins"))
async def cmd_admins_list_pm(message: Message):
    """Просмотр списка администраторов и шефа."""
    if not await check_admin_or_boss(message.from_user.id):
        return
    boss_id = await db.get_boss_id()
    admins = await db.get_all_admins()
    text = (
        f"👑 <b>Главный Шеф:</b> <code>{boss_id}</code>\n\n"
        f"🛡 <b>Администраторы ({len(admins)}):</b>\n"
    )
    for idx, a in enumerate(admins, 1):
        text += f"{idx}. <b>{a['name']}</b> (ID: <code>{a['user_id']}</code>)\n"
    await message.answer(text)


@router.callback_query(F.data == "cfg:schedule")
async def cb_schedule_menu(cb: CallbackQuery):
    await cb.answer()
    text = (
        "⚙️ <b>НАСТРОЙКИ АВТОМАТИЧЕСКИХ ОТЧЕТОВ ШЕФУ:</b>\n\n"
        f"• Еженедельный отчет: <b>{'ВКЛ' if config.WEEKLY_REPORT_ENABLED else 'ВЫКЛ'}</b> (Понедельник, 09:00)\n"
        f"• Ежемесячный отчет: <b>{'ВКЛ' if config.MONTHLY_REPORT_ENABLED else 'ВЫКЛ'}</b> (1-е число месяца, 09:00)\n\n"
        f"Отчеты с графиками и Excel-таблицами автоматически приходят вам в этот чат."
    )
    await cb.message.edit_text(
        text,
        reply_markup=schedule_settings_kb(config.WEEKLY_REPORT_ENABLED, config.MONTHLY_REPORT_ENABLED)
    )


@router.callback_query(F.data == "cfg:toggle_weekly")
async def cb_toggle_weekly(cb: CallbackQuery):
    config.WEEKLY_REPORT_ENABLED = not config.WEEKLY_REPORT_ENABLED
    await cb.answer(f"Еженедельный отчет: {'ВКЛ' if config.WEEKLY_REPORT_ENABLED else 'ВЫКЛ'}")
    await cb_schedule_menu(cb)


@router.callback_query(F.data == "cfg:toggle_monthly")
async def cb_toggle_monthly(cb: CallbackQuery):
    config.MONTHLY_REPORT_ENABLED = not config.MONTHLY_REPORT_ENABLED
    await cb.answer(f"Ежемесячный отчет: {'ВКЛ' if config.MONTHLY_REPORT_ENABLED else 'ВЫКЛ'}")
    await cb_schedule_menu(cb)


# =========================================================================
# 3. АНАЛИЗ ФАЙЛА ЭКСПОРТА ЧАТА (result.json ИЗ TELEGRAM DESKTOP)
# =========================================================================

@router.message(F.chat.type == "private", F.document)
async def on_document_upload(message: Message, bot: Bot):
    """
    Прием файла экспорта истории чата result.json из Telegram Desktop.
    Позволяет мгновенно получить отчет по любому существующему чату магазина!
    """
    if not await check_admin_or_boss(message.from_user.id):
        return

    doc = message.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".json"):
        return await message.answer("ℹ️ Для анализа истории чата отправьте файл экспорта в формате <code>result.json</code>.")

    status_msg = await message.answer("⏳ Загружаю и анализирую историю чата... Пожалуйста, подождите.")
    try:
        downloads_dir = config.BASE_DIR / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        local_json_path = downloads_dir / f"export_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        await bot.download(doc.file_id, destination=local_json_path)

        # Список менеджеров для классификации
        managers = await db.get_all_managers()
        manager_names = [m["name"] for m in managers] + [str(m["user_id"]) for m in managers]

        # Анализ истории
        stats = analyze_telegram_export_json(str(local_json_path), manager_names_or_ids=manager_names)
        rep_text = generate_telegram_text(stats)

        # Генерация Excel
        reports_dir = config.BASE_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        excel_path = str(reports_dir / f"export_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        generate_excel_file(stats, excel_path)

        await status_msg.delete()
        await message.answer(f"📁 <b>АНАЛИЗ ИСТОРИИ ЧАТА ИЗ ФАЙЛА</b>\n\n{rep_text}")

        excel_doc = FSInputFile(excel_path, filename=f"Анализ_Архива_{doc.file_name.replace('.json', '.xlsx')}")
        await message.answer_document(
            document=excel_doc,
            caption="📑 Детализированная таблица Excel по загруженному архиву чата."
        )

    except Exception as e:
        log.exception("Failed to analyze uploaded JSON: %s", e)
        await status_msg.edit_text(f"❌ Ошибка при анализе файла: {e}")
