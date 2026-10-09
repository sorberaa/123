"""База данных для сохранения сообщений, статистики и метрик отчетов."""
import os
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DATABASE_PATH

def get_db_path() -> str:
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
    return DATABASE_PATH

async def init_db() -> None:
    """Инициализация таблиц базы данных SQLite."""
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                chat_title TEXT DEFAULT '',
                user_id INTEGER NOT NULL,
                user_name TEXT DEFAULT '',
                user_handle TEXT DEFAULT '',
                is_manager INTEGER DEFAULT 0,
                reply_to_msg_id INTEGER,
                text TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                category_title TEXT DEFAULT '❓ Прочие вопросы',
                is_question INTEGER DEFAULT 0,
                UNIQUE(chat_id, message_id)
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS response_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                question_msg_id INTEGER NOT NULL,
                question_time TEXT NOT NULL,
                reply_msg_id INTEGER NOT NULL,
                reply_time TEXT NOT NULL,
                client_id INTEGER NOT NULL,
                client_name TEXT DEFAULT '',
                manager_id INTEGER NOT NULL,
                manager_name TEXT DEFAULT '',
                category TEXT DEFAULT 'other',
                response_time_seconds REAL NOT NULL,
                UNIQUE(chat_id, reply_msg_id)
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                event_type TEXT NOT NULL, -- 'join' или 'leave'
                user_id INTEGER NOT NULL,
                user_name TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS managers (
                user_id INTEGER PRIMARY KEY,
                name TEXT DEFAULT '',
                added_at TEXT DEFAULT (datetime('now'))
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT DEFAULT '',
                added_at TEXT DEFAULT (datetime('now'))
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # Индексы для быстрого сбора аналитики по периодам
        await db.execute("CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(timestamp);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON chat_events(timestamp);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_resp_ts ON response_times(reply_time);")

        await db.commit()


# ================== РАБОТА С МЕНЕДЖЕРАМИ ==================

async def is_manager(user_id: int) -> bool:
    """Проверка, является ли пользователь зарегистрированным менеджером поддержки."""
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute("SELECT 1 FROM managers WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def add_manager(user_id: int, name: str) -> None:
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "INSERT OR REPLACE INTO managers (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )
        await db.commit()

async def remove_manager(user_id: int) -> None:
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM managers WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_all_managers() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, name, added_at FROM managers ORDER BY name") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ================== ОТСЛЕЖИВАЕМЫЕ ЧАТЫ ==================

async def save_tracked_chat(chat_id: int, chat_title: str) -> None:
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "INSERT OR REPLACE INTO tracked_chats (chat_id, chat_title) VALUES (?, ?)",
            (chat_id, chat_title)
        )
        await db.commit()

async def get_tracked_chats() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT chat_id, chat_title, added_at FROM tracked_chats") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ================== СООБЩЕНИЯ И СОБЫТИЯ ==================

async def save_message(
    message_id: int,
    chat_id: int,
    chat_title: str,
    user_id: int,
    user_name: str,
    user_handle: str,
    is_mgr: bool,
    reply_to_msg_id: Optional[int],
    text: str,
    timestamp: str,
    category: str,
    category_title: str,
    is_question: bool
) -> None:
    """Сохранение сообщения в базу данных."""
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            INSERT OR REPLACE INTO messages (
                message_id, chat_id, chat_title, user_id, user_name, user_handle,
                is_manager, reply_to_msg_id, text, timestamp, category,
                category_title, is_question
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id, chat_id, chat_title, user_id, user_name, user_handle,
            1 if is_mgr else 0, reply_to_msg_id, text, timestamp, category,
            category_title, 1 if is_question else 0
        ))
        await db.commit()

async def get_message(chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
    """Поиск сообщения по ID чата и ID сообщения."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def record_response_time(
    chat_id: int,
    question_msg_id: int,
    question_time: str,
    reply_msg_id: int,
    reply_time: str,
    client_id: int,
    client_name: str,
    manager_id: int,
    manager_name: str,
    category: str,
    response_time_seconds: float
) -> None:
    """Запись замера скорости ответа менеджера."""
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            INSERT OR REPLACE INTO response_times (
                chat_id, question_msg_id, question_time, reply_msg_id, reply_time,
                client_id, client_name, manager_id, manager_name, category, response_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id, question_msg_id, question_time, reply_msg_id, reply_time,
            client_id, client_name, manager_id, manager_name, category, response_time_seconds
        ))
        await db.commit()

async def record_chat_event(chat_id: int, event_type: str, user_id: int, user_name: str, timestamp: str) -> None:
    """Запись события входа или выхода участника."""
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "INSERT INTO chat_events (chat_id, event_type, user_id, user_name, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chat_id, event_type, user_id, user_name, timestamp)
        )
        await db.commit()


# ================== ВЫБОРКА ДАННЫХ ДЛЯ АНАЛИТИКИ ==================

async def fetch_messages_for_period(start_iso: str, end_iso: str, chat_id: Optional[int] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM messages WHERE timestamp >= ? AND timestamp <= ?"
    params: List[Any] = [start_iso, end_iso]
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY timestamp ASC"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def fetch_response_times_for_period(start_iso: str, end_iso: str, chat_id: Optional[int] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM response_times WHERE reply_time >= ? AND reply_time <= ?"
    params: List[Any] = [start_iso, end_iso]
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY reply_time ASC"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def fetch_events_for_period(start_iso: str, end_iso: str, chat_id: Optional[int] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM chat_events WHERE timestamp >= ? AND timestamp <= ?"
    params: List[Any] = [start_iso, end_iso]
    if chat_id is not None:
        query += " AND chat_id = ?"
        params.append(chat_id)
    query += " ORDER BY timestamp ASC"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
