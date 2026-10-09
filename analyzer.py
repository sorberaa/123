"""Модуль расчета метрик, аналитики и классификации активности чата."""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import statistics
from collections import Counter
import re

from categories import classify_text, is_question_message, CATEGORIES_DEF

def format_duration(seconds: float) -> str:
    """Форматирует секунды в человекопонятное время (мин, сек, ч)."""
    if seconds < 60:
        return f"{int(seconds)} сек"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} мин {int(seconds % 60)} сек"
    hours = minutes / 60
    remaining_min = int(minutes % 60)
    return f"{int(hours)} ч {remaining_min} мин"

def make_progress_bar(pct: float, total_blocks: int = 10) -> str:
    """Генерирует визуальный прогресс-бар из кубиков."""
    filled = int(round((pct / 100.0) * total_blocks))
    filled = max(0, min(total_blocks, filled))
    return "🟩" * filled + "⬜" * (total_blocks - filled)

def compute_analytics(
    messages: List[Dict[str, Any]],
    response_records: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    period_title: str
) -> Dict[str, Any]:
    """
    Рассчитывает полную аналитику для отчета шефу:
    - Объем сообщений (клиенты / менеджеры)
    - Новые участники
    - Категории вопросов (боли клиентов)
    - Скорость ответов поддержки
    - Эффективность каждого менеджера
    """
    total_messages = len(messages)
    client_messages = [m for m in messages if not m.get("is_manager")]
    manager_messages = [m for m in messages if m.get("is_manager")]

    joins_count = sum(1 for e in events if e.get("event_type") == "join")
    leaves_count = sum(1 for e in events if e.get("event_type") == "leave")
    net_growth = joins_count - leaves_count

    # --- Анализ вопросов и болей клиентов ---
    questions = [m for m in client_messages if m.get("is_question")]
    total_questions = len(questions)

    category_counts: Counter = Counter()
    for q in questions:
        cat = q.get("category", "other")
        category_counts[cat] += 1

    category_stats = []
    for cat_key, count in category_counts.most_common():
        pct = (count / total_questions * 100) if total_questions > 0 else 0
        cat_info = CATEGORIES_DEF.get(cat_key, {"title": "❓ Прочие вопросы", "emoji": "❓"})
        category_stats.append({
            "key": cat_key,
            "title": cat_info["title"],
            "emoji": cat_info["emoji"],
            "count": count,
            "pct": round(pct, 1),
            "progress_bar": make_progress_bar(pct, 8)
        })

    # --- Анализ скорости ответов (Response Times) ---
    durations = [r["response_time_seconds"] for r in response_records if r.get("response_time_seconds") is not None]
    total_replies = len(durations)

    if durations:
        avg_seconds = statistics.mean(durations)
        median_seconds = statistics.median(durations)
        min_seconds = min(durations)
        max_seconds = max(durations)

        fast_under_5m = sum(1 for s in durations if s <= 300)
        under_15m = sum(1 for s in durations if s <= 900)
        under_1h = sum(1 for s in durations if s <= 3600)
        over_1h = sum(1 for s in durations if s > 3600)

        pct_under_5m = round(fast_under_5m / total_replies * 100, 1)
        pct_under_15m = round(under_15m / total_replies * 100, 1)
        pct_over_1h = round(over_1h / total_replies * 100, 1)
    else:
        avg_seconds = 0
        median_seconds = 0
        min_seconds = 0
        max_seconds = 0
        pct_under_5m = 0
        pct_under_15m = 0
        pct_over_1h = 0

    # --- Статистика по менеджерам ---
    mgr_stats: Dict[int, Dict[str, Any]] = {}
    for r in response_records:
        mid = r["manager_id"]
        mname = r.get("manager_name") or f"Менеджер #{mid}"
        if mid not in mgr_stats:
            mgr_stats[mid] = {"name": mname, "times": [], "count": 0}
        mgr_stats[mid]["times"].append(r["response_time_seconds"])
        mgr_stats[mid]["count"] += 1

    managers_summary = []
    for mid, data in mgr_stats.items():
        avg_t = statistics.mean(data["times"]) if data["times"] else 0
        med_t = statistics.median(data["times"]) if data["times"] else 0
        managers_summary.append({
            "manager_id": mid,
            "name": data["name"],
            "replies_count": data["count"],
            "avg_time_str": format_duration(avg_t),
            "median_time_str": format_duration(med_t),
            "avg_seconds": avg_t
        })
    # Сортируем менеджеров по числу ответов
    managers_summary.sort(key=lambda x: x["replies_count"], reverse=True)

    # --- Активность по часам (пиковые часы вопросов) ---
    hour_counts: Counter = Counter()
    for m in client_messages:
        try:
            ts = m.get("timestamp", "")
            if "T" in ts:
                hour = int(ts.split("T")[1].split(":")[0])
            elif " " in ts:
                hour = int(ts.split(" ")[1].split(":")[0])
            else:
                continue
            hour_counts[hour] += 1
        except Exception:
            pass

    peak_hours = hour_counts.most_common(3)
    peak_hours_str = ", ".join([f"{h:02d}:00–{h+1:02d}:00 ({cnt} сообщ.)" for h, cnt in peak_hours]) if peak_hours else "Равномерно"

    return {
        "period_title": period_title,
        "total_messages": total_messages,
        "client_messages_count": len(client_messages),
        "manager_messages_count": len(manager_messages),
        "joins_count": joins_count,
        "leaves_count": leaves_count,
        "net_growth": net_growth,
        "total_questions": total_questions,
        "category_stats": category_stats,
        "total_replies": total_replies,
        "avg_response_time": format_duration(avg_seconds),
        "median_response_time": format_duration(median_seconds),
        "min_response_time": format_duration(min_seconds),
        "max_response_time": format_duration(max_seconds),
        "pct_under_5m": pct_under_5m,
        "pct_under_15m": pct_under_15m,
        "pct_over_1h": pct_over_1h,
        "managers_summary": managers_summary,
        "peak_hours_str": peak_hours_str,
        "raw_messages": messages,
        "raw_responses": response_records
    }
