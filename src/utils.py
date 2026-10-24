"""Загрузка и подготовка данных о банковских транзакциях.

Модуль отвечает только за получение данных из Excel-файла и их приведение
к единому виду. Бизнес-логика (views, services, reports) получает готовый
DataFrame и не знает, откуда он взялся.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATA_FILE = DATA_DIR / "operations.xlsx"
DEFAULT_SETTINGS_FILE = PROJECT_ROOT / "user_settings.json"

DATE_FORMAT = "%d.%m.%Y"
DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"

DATE_COLUMN = "Дата операции"
PAYMENT_DATE_COLUMN = "Дата платежа"
CARD_COLUMN = "Номер карты"
STATUS_COLUMN = "Статус"
AMOUNT_COLUMN = "Сумма операции"
PAYMENT_AMOUNT_COLUMN = "Сумма платежа"
CURRENCY_COLUMN = "Валюта операции"
PAYMENT_CURRENCY_COLUMN = "Валюта платежа"
CASHBACK_COLUMN = "Кэшбэк"
CATEGORY_COLUMN = "Категория"
MCC_COLUMN = "MCC"
DESCRIPTION_COLUMN = "Описание"
INVEST_ROUNDING_COLUMN = "Округление на инвесткопилку"
ROUNDED_AMOUNT_COLUMN = "Сумма операции с округлением"

STATUS_OK = "OK"
UNKNOWN_CATEGORY = "Без категории"
TRANSFER_CATEGORIES = ("Переводы", "Наличные")


def read_transactions(file_path: str | Path) -> pd.DataFrame:
    """Считывает транзакции из Excel-файла (.xlsx или .xls).

    Имя файла передаётся только здесь, чтобы бизнес-логика не зависела
    от источника данных.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл с транзакциями не найден: {path}")

    logger.info("Чтение транзакций из файла %s", path)
    frame = pd.read_excel(path, sheet_name=0)
    logger.info("Прочитано строк: %d, колонок: %d", *frame.shape)
    return prepare_transactions(frame)


def prepare_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Приводит «сырой» DataFrame к рабочему виду.

    * даты -> datetime;
    * суммы и кешбэк -> числа;
    * категория -> строка (пропуски заменяются на «Без категории»);
    * добавляется колонка ``last_digits`` с последними 4 цифрами карты.
    """
    result = frame.copy()

    for column in (DATE_COLUMN, PAYMENT_DATE_COLUMN):
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column], format="mixed", dayfirst=True, errors="coerce"
            )

    numeric_columns = (
        AMOUNT_COLUMN,
        PAYMENT_AMOUNT_COLUMN,
        CASHBACK_COLUMN,
        MCC_COLUMN,
        INVEST_ROUNDING_COLUMN,
        ROUNDED_AMOUNT_COLUMN,
    )
    for column in numeric_columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    for column in (
        STATUS_COLUMN,
        CATEGORY_COLUMN,
        DESCRIPTION_COLUMN,
        CURRENCY_COLUMN,
        PAYMENT_CURRENCY_COLUMN,
    ):
        if column in result.columns:
            result[column] = result[column].astype("string").fillna("").str.strip()

    if CATEGORY_COLUMN in result.columns:
        result[CATEGORY_COLUMN] = result[CATEGORY_COLUMN].replace(
            "", UNKNOWN_CATEGORY
        )

    if CARD_COLUMN in result.columns:
        result[CARD_COLUMN] = result[CARD_COLUMN].astype("string").fillna("")
        result["last_digits"] = result[CARD_COLUMN].map(last_digits)

    return result


def last_digits(value: Any) -> str:
    """Возвращает последние 4 цифры номера карты либо пустую строку."""
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-4:]


def filter_successful(frame: pd.DataFrame) -> pd.DataFrame:
    """Оставляет только успешно проведённые операции (статус OK)."""
    return frame[frame[STATUS_COLUMN] == STATUS_OK]


def filter_period(
    frame: pd.DataFrame, start: datetime, end: datetime
) -> pd.DataFrame:
    """Оставляет операции, попавшие в диапазон [start, end]."""
    dates = frame[DATE_COLUMN]
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return frame[mask]


def parse_datetime(value: str | datetime) -> datetime:
    """Разбирает дату в формате ``YYYY-MM-DD HH:MM:SS`` (и родственных)."""
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    for fmt in (DATETIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d", DATE_FORMAT, "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Не удалось разобрать дату: {value!r}")
    return parsed.to_pydatetime()


def month_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Границы месяца, на который выпадает дата: с 1-го числа по саму дату."""
    start = moment.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end = moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def week_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Границы недели (с понедельника) по дату включительно."""
    start = (
        pd.Timestamp(moment) - pd.Timedelta(days=moment.weekday())
    ).to_pydatetime()
    end = moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def year_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """Границы года: с 1 января по дату включительно."""
    start = moment.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end = moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def all_time_bounds(
    frame: pd.DataFrame, moment: datetime
) -> tuple[datetime, datetime]:
    """Диапазон «все данные до указанной даты»."""
    earliest = frame[DATE_COLUMN].min()
    start = earliest.to_pydatetime() if pd.notna(earliest) else moment
    end = moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def get_period_bounds(
    frame: pd.DataFrame, moment: datetime, period: str = "M"
) -> tuple[datetime, datetime]:
    """Возвращает границы периода по коду W/M/Y/ALL."""
    code = (period or "M").upper()
    if code == "W":
        return week_bounds(moment)
    if code == "Y":
        return year_bounds(moment)
    if code == "ALL":
        return all_time_bounds(frame, moment)
    return month_bounds(moment)


def ensure_frame(data: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    """Превращает список словарей в DataFrame, а DataFrame — в копию."""
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
        if DATE_COLUMN in frame.columns and not pd.api.types.is_datetime64_any_dtype(
            frame[DATE_COLUMN]
        ):
            return prepare_transactions(frame)
        return frame
    return prepare_transactions(pd.DataFrame(data))


def format_date(value: Any) -> str:
    """Форматирует дату как dd.mm.yyyy."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return timestamp.strftime(DATE_FORMAT)


def to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Преобразует DataFrame в список JSON-совместимых словарей."""
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                "date": format_date(row.get(DATE_COLUMN)),
                "card": row.get("last_digits") or last_digits(row.get(CARD_COLUMN)),
                "status": row.get(STATUS_COLUMN, ""),
                "amount": _to_float(row.get(PAYMENT_AMOUNT_COLUMN)),
                "currency": row.get(PAYMENT_CURRENCY_COLUMN, ""),
                "category": row.get(CATEGORY_COLUMN, ""),
                "description": row.get(DESCRIPTION_COLUMN, ""),
            }
        )
    return records


def _to_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(number):
        return 0.0
    return round(number, 2)


def load_user_settings(path: str | Path = DEFAULT_SETTINGS_FILE) -> dict[str, Any]:
    """Читает пользовательские настройки (валюты и акции)."""
    settings_path = Path(path)
    defaults: dict[str, Any] = {"user_currencies": ["USD", "EUR"],
                                "user_stocks": ["AAPL", "AMZN", "GOOGL",
                                                "MSFT", "TSLA"]}
    if not settings_path.exists():
        logger.warning("Файл настроек %s не найден, взяты значения по умолчанию",
                       settings_path)
        return defaults

    try:
        with settings_path.open("r", encoding="utf-8") as file:
            settings = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        logger.error("Не удалось прочитать настройки %s: %s", settings_path, error)
        return defaults

    result = dict(defaults)
    result.update(settings)
    return result


def round_money(value: float, digits: int = 2) -> float:
    """Округляет денежную сумму."""
    return round(float(value) + 0.0, digits)
