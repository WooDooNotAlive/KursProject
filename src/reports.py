"""Отчёты по транзакциям и декоратор сохранения результатов."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from src import utils

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
WEEKDAYS = ("Понедельник", "Вторник", "Среда", "Четверг",
            "Пятница", "Суббота", "Воскресенье")
REPORT_COLUMNS = ("Дата операции", "Категория", "Сумма", "Описание")


def _default_report_path(function_name: str) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return REPORTS_DIR / f"{function_name}_{stamp}.csv"


def _save_report(result: Any, path: Path) -> None:
    """Сохраняет результат отчёта в файл (CSV, JSON или текст)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if isinstance(result, pd.DataFrame):
            if path.suffix.lower() != ".csv":
                path = path.with_suffix(".csv")
            result.to_csv(path, index=False, sep=";", encoding="utf-8-sig")
        elif isinstance(result, (dict, list)):
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")
            path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            if path.suffix.lower() not in (".txt", ".md"):
                path = path.with_suffix(".txt")
            path.write_text(str(result), encoding="utf-8")
    except OSError as error:
        logger.error("Не удалось сохранить отчёт %s: %s", path, error)
        return

    logger.info("Отчёт сохранён: %s", path)


def report(
    filename: Optional[str | Callable[..., Any]] = None,
) -> Callable[..., Any]:
    """Декоратор, сохраняющий результат функции-отчёта в файл.

    Использование без параметра — имя файла генерируется автоматически::

        @report
        def my_report(...): ...

    Использование с параметром — имя файла задаётся явно::

        @report("category_spending.csv")
        def my_report(...): ...
    """

    def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = function(*args, **kwargs)
            target = (
                Path(filename)
                if isinstance(filename, str) and filename
                else _default_report_path(function.__name__)
            )
            _save_report(result, target)
            return result

        return wrapper

    if callable(filename):
        function = filename
        filename = None
        return decorator(function)

    return decorator


def _prepare(
    transactions: pd.DataFrame | list[dict[str, Any]], date: Optional[str]
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Готовит данные и границы периода «последние три месяца»."""
    frame = utils.filter_successful(utils.ensure_frame(transactions))
    end = (
        pd.Timestamp(utils.parse_datetime(date))
        if date
        else pd.Timestamp(datetime.now())
    )
    start = end - pd.DateOffset(months=3)
    mask = (
        (frame[utils.DATE_COLUMN] > start)
        & (frame[utils.DATE_COLUMN] <= end)
        & (frame[utils.PAYMENT_AMOUNT_COLUMN] < 0)
    )
    frame = frame[mask]
    return frame, start, end


@report
def spending_by_category(
    transactions: pd.DataFrame,
    category: str,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Траты по заданной категории за последние три месяца."""
    frame, start, end = _prepare(transactions, date)
    selected = frame[
        frame[utils.CATEGORY_COLUMN].str.casefold() == category.strip().casefold()
    ]

    result = pd.DataFrame(
        {
            "Дата операции": selected[utils.DATE_COLUMN].dt.strftime(
                utils.DATE_FORMAT
            ),
            "Категория": selected[utils.CATEGORY_COLUMN],
            "Сумма": selected[utils.PAYMENT_AMOUNT_COLUMN].abs().round(2),
            "Описание": selected[utils.DESCRIPTION_COLUMN],
        }
    )
    result = result.sort_values("Дата операции", ascending=False)
    logger.info(
        "Траты по категории %s за %s - %s: %d операций",
        category,
        start.strftime(utils.DATE_FORMAT),
        end.strftime(utils.DATE_FORMAT),
        len(result),
    )
    return result.reset_index(drop=True)


def _daily_totals(frame: pd.DataFrame) -> pd.Series:
    """Суммарные траты по дням."""
    if frame.empty:
        return pd.Series(dtype="float64")
    daily = frame.groupby(
        frame[utils.DATE_COLUMN].dt.normalize()
    )[utils.PAYMENT_AMOUNT_COLUMN].sum()
    return daily.abs()


@report
def spending_by_weekday(
    transactions: pd.DataFrame,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Средние траты в каждый день недели за последние три месяца."""
    frame, _, _ = _prepare(transactions, date)
    daily = _daily_totals(frame)

    if daily.empty:
        return pd.DataFrame(columns=["День недели", "Средние траты"])

    by_weekday = daily.groupby(daily.index.day_of_week).mean()
    rows = [
        {
            "День недели": name,
            "Средние траты": round(float(by_weekday.get(index, 0.0)), 2),
        }
        for index, name in enumerate(WEEKDAYS)
    ]
    return pd.DataFrame(rows, columns=["День недели", "Средние траты"])


@report
def spending_by_workday(
    transactions: pd.DataFrame,
    date: Optional[str] = None,
) -> pd.DataFrame:
    """Средние траты в рабочий и в выходной день за три месяца."""
    frame, _, _ = _prepare(transactions, date)
    daily = _daily_totals(frame)

    columns = ["Тип дня", "Средние траты"]
    if daily.empty:
        return pd.DataFrame(columns=columns)

    is_workday = daily.index.day_of_week < 5
    values = {
        "Рабочий день": float(daily[is_workday].mean()) if is_workday.any() else 0.0,
        "Выходной день": (
            float(daily[~is_workday].mean()) if (~is_workday).any() else 0.0
        ),
    }
    rows = [
        {"Тип дня": name, "Средние траты": round(value, 2)}
        for name, value in values.items()
    ]
    return pd.DataFrame(rows, columns=columns)
