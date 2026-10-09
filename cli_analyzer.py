"""Автономный консольный скрипт для анализа экспорта чата Telegram (result.json)."""
import sys
import argparse
from pathlib import Path

from json_importer import analyze_telegram_export_json
from reporter import generate_telegram_text, generate_excel_file


def main():
    parser = argparse.ArgumentParser(description="Анализатор чата магазина для шефа (по файлу result.json)")
    parser.add_argument("file", help="Путь к файлу экспорта result.json")
    parser.add_argument("--days", type=int, default=None, help="Ограничить анализ последними N днями (например, 7 или 30)")
    parser.add_argument("--managers", nargs="*", default=[], help="Имена или ID менеджеров (через пробел)")
    parser.add_argument("--excel", default=None, help="Путь для сохранения Excel отчета (например, report.xlsx)")

    args = parser.parse_args()
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Ошибка: файл {input_path} не найден!")
        sys.exit(1)

    print(f"[*] Анализирую {input_path} (дней: {args.days or 'все'})...")
    stats = analyze_telegram_export_json(str(input_path), days=args.days, manager_names_or_ids=args.managers)

    print("\n" + "=" * 50)
    # Печать текстового отчета без тегов HTML
    text_report = generate_telegram_text(stats)
    clean_text = text_report.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
    print(clean_text)
    print("=" * 50 + "\n")

    if args.excel:
        excel_path = Path(args.excel)
        generate_excel_file(stats, str(excel_path))
        print(f"[+] Таблица Excel сохранена в: {excel_path.resolve()}")


if __name__ == "__main__":
    main()
