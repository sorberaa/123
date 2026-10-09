"""Импортер и анализатор экспорта истории чата Telegram Desktop (result.json)."""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from categories import classify_text, is_question_message
from analyzer import compute_analytics

def parse_text_content(raw_text: Any) -> str:
    """Извлекает чистый текст из поля text сообщения (может быть строкой или массивом сущностей)."""
    if isinstance(raw_text, str):
        return raw_text
    if isinstance(raw_text, list):
        parts = []
        for item in raw_text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts)
    return ""

def analyze_telegram_export_json(
    file_path: str,
    days: Optional[int] = None,
    manager_names_or_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Парсит файл экспорта result.json из Telegram Desktop и строит полную аналитику.
    manager_names_or_ids: список имен или ID менеджеров, чтобы отличать их от клиентов.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chat_name = data.get("name", "Чат магазина")
    raw_messages = data.get("messages", [])

    manager_identifiers = set([str(x).lower().strip() for x in (manager_names_or_ids or [])])

    parsed_messages = []
    events = []
    messages_by_id = {}

    cutoff_date = None
    if days:
        cutoff_date = datetime.now() - timedelta(days=days)

    for msg in raw_messages:
        date_str = msg.get("date", "")
        if not date_str:
            continue
        try:
            msg_dt = datetime.fromisoformat(date_str)
        except Exception:
            continue

        if cutoff_date and msg_dt < cutoff_date:
            continue

        msg_type = msg.get("type", "message")
        msg_id = msg.get("id")

        if msg_type == "service":
            action = msg.get("action", "")
            actor = msg.get("actor", msg.get("from", "Участник"))
            if action in ("join_group_by_link", "invite_members", "join_group"):
                events.append({
                    "event_type": "join",
                    "user_name": actor,
                    "timestamp": date_str
                })
            elif action in ("leave_group", "remove_members"):
                events.append({
                    "event_type": "leave",
                    "user_name": actor,
                    "timestamp": date_str
                })
            continue

        # Обычное текстовое сообщение
        sender_name = msg.get("from", "Аноним")
        sender_id = str(msg.get("from_id", ""))
        text = parse_text_content(msg.get("text", ""))

        is_mgr = (
            sender_id.lower() in manager_identifiers
            or sender_name.lower() in manager_identifiers
            or "менеджер" in sender_name.lower()
            or "админ" in sender_name.lower()
            or "поддержка" in sender_name.lower()
            or "support" in sender_name.lower()
        )

        cat_key, cat_title = classify_text(text)
        is_q = is_question_message(text)

        parsed_msg = {
            "message_id": msg_id,
            "user_id": sender_id,
            "user_name": sender_name,
            "is_manager": is_mgr,
            "reply_to_msg_id": msg.get("reply_to_message_id"),
            "text": text,
            "timestamp": date_str,
            "dt": msg_dt,
            "category": cat_key,
            "category_title": cat_title,
            "is_question": is_q
        }
        parsed_messages.append(parsed_msg)
        messages_by_id[msg_id] = parsed_msg

    # Расчет времени ответа менеджеров на вопросы клиентов
    response_records = []
    for msg in parsed_messages:
        reply_to_id = msg.get("reply_to_msg_id")
        if reply_to_id and msg["is_manager"]:
            parent = messages_by_id.get(reply_to_id)
            if parent and not parent["is_manager"]:
                diff_seconds = (msg["dt"] - parent["dt"]).total_seconds()
                if diff_seconds >= 0:
                    response_records.append({
                        "question_msg_id": parent["message_id"],
                        "question_time": parent["timestamp"],
                        "reply_msg_id": msg["message_id"],
                        "reply_time": msg["timestamp"],
                        "client_id": parent["user_id"],
                        "client_name": parent["user_name"],
                        "manager_id": msg["user_id"],
                        "manager_name": msg["user_name"],
                        "category": parent["category_title"],
                        "response_time_seconds": diff_seconds
                    })

    period_title = f"Последние {days} дней ({chat_name})" if days else f"Вся история чата ({chat_name})"
    return compute_analytics(parsed_messages, response_records, events, period_title)
