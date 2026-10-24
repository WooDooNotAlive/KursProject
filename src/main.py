"""Демонстрация работы всех сервисов приложения.

Запуск из корня проекта::

    python -m src.main
    python -m src.main --date "2021-12-31 16:44:00" --period M
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from src import reports, services, utils, views
from src.logger import setup_logging


def print_json(title: str, payload: Any) -> None:
    """Печатает заголовок и JSON-ответ."""
    print(f"\n===== {title} =====")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    """Точка входа демонстрационного сценария."""
    setup_logging()

    parser = argparse.ArgumentParser(description="Анализ банковских транзакций")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        help="Дата и время в формате 'YYYY-MM-DD HH:MM:SS'",
    )
    parser.add_argument(
        "--period",
        default="M",
        choices=["W", "M", "Y", "ALL"],
        help="Диапазон для страницы «События»",
    )
    args = parser.parse_args()

    frame = utils.read_transactions(utils.DEFAULT_DATA_FILE)
    print(f"Загружено операций: {len(frame)}")

    print_json("Главная страница", views.main_page(args.date, frame))
    print_json(
        f"События (период {args.period})",
        views.events_page(args.date, args.period, frame),
    )

    moment = utils.parse_datetime(args.date)
    cashback = services.cashback_categories(
        frame, moment.year, moment.month
    )
    print_json("Кешбэк по категориям (топ-3)", dict(list(cashback.items())[:3]))

    month = moment.strftime("%Y-%m")
    saved = services.investment_bank(month, frame, limit=50)
    print(f"\nИнвесткопилка за {month} (шаг 50 ₽): {saved} ₽")

    found = services.simple_search(frame, "магнит")
    print(f"Простой поиск «магнит»: найдено {len(found)} операций")

    phones = services.phone_search(frame)
    print(f"Поиск по телефонам: найдено {len(phones)} операций")

    people = services.transfers_to_people(frame)
    print(f"Переводы физлицам: найдено {len(people)} операций")

    category_report = reports.spending_by_category(
        frame, "Супермаркеты", args.date
    )
    print(f"\nТраты по категории «Супермаркеты»: {len(category_report)} операций")

    weekday_report = reports.spending_by_weekday(frame, args.date)
    print("\nСредние траты по дням недели:")
    print(weekday_report.to_string(index=False))

    workday_report = reports.spending_by_workday(frame, args.date)
    print("\nСредние траты в рабочий/выходной день:")
    print(workday_report.to_string(index=False))

    print("\nОтчёты сохранены в папку reports/")


if __name__ == "__main__":
    main()
