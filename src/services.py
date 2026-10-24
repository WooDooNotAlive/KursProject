"""Сервисы анализа транзакций.

Модуль построен на элементах функционального программирования:
фильтрация, свёртка (``functools.reduce``), сортировка и генераторы.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from functools import reduce
from typing import Any, Iterable

import pandas as pd

from src import utils

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+7|8)(?:[\s\-()]*\d){9,10}(?!\d)"
)
PERSON_PATTERN = re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.")


def _matches_phone(text: str) -> bool:
    """Проверяет, есть ли в тексте мобильный номер в любом формате."""
    for match in PHONE_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) in (10, 11) and digits[0] in "78":
            return True
    return False


def cashback_categories(
    data: pd.DataFrame | list[dict[str, Any]],
    year: int,
    month: int,
    rate: float = 0.01,
) -> dict[str, int]:
    """Считает, сколько кешбэка можно получить по каждой категории.

    Анализируются расходные операции за указанный месяц. Категории
    «Переводы» и «Наличные» исключены: кешбэк по ним не начисляется.
    """
    if not 1 <= int(month) <= 12:
        raise ValueError("Месяц должен быть в диапазоне 1..12")

    frame = utils.ensure_frame(data)
    frame = utils.filter_successful(frame)
    period = frame[
        (frame[utils.DATE_COLUMN].dt.year == int(year))
        & (frame[utils.DATE_COLUMN].dt.month == int(month))
    ]
    expenses = period[period[utils.PAYMENT_AMOUNT_COLUMN] < 0]
    expenses = expenses[
        ~expenses[utils.CATEGORY_COLUMN].isin(utils.TRANSFER_CATEGORIES)
    ]

    if expenses.empty:
        return {}

    totals: Iterable[tuple[str, float]] = (
        (str(category), float(amount))
        for category, amount in expenses.groupby(utils.CATEGORY_COLUMN)[
            utils.PAYMENT_AMOUNT_COLUMN
        ].sum().items()
    )

    def accumulate(
        accumulator: dict[str, int], item: tuple[str, float]
    ) -> dict[str, int]:
        category, amount = item
        accumulator[category] = int(round(abs(amount) * rate))
        return accumulator

    result: dict[str, int] = reduce(accumulate, totals, {})
    return dict(
        sorted(result.items(), key=lambda pair: pair[1], reverse=True)
    )


def investment_bank(
    month: str,
    transactions: list[dict[str, Any]] | pd.DataFrame,
    limit: int,
) -> float:
    """Считает сумму, которую удалось бы отложить в «Инвесткопилку».

    ``month`` — строка ``YYYY-MM``, ``limit`` — шаг округления (10/50/100).
    """
    if int(limit) <= 0:
        raise ValueError("Предел округления должен быть больше нуля")

    frame = utils.ensure_frame(transactions)
    if utils.STATUS_COLUMN in frame.columns:
        frame = utils.filter_successful(frame)
    start = datetime.strptime(month, "%Y-%m")

    def is_target(row: pd.Series) -> bool:
        moment = row[utils.DATE_COLUMN]
        return (
            pd.notna(moment)
            and moment.year == start.year
            and moment.month == start.month
            and float(row[utils.AMOUNT_COLUMN]) < 0
        )

    target = frame[frame.apply(is_target, axis=1)]
    if target.empty:
        return 0.0

    def round_up(value: float, step: int) -> float:
        return math.ceil(abs(value) / step) * step

    saved = sum(
        round_up(float(amount), int(limit)) - abs(float(amount))
        for amount in target[utils.AMOUNT_COLUMN]
    )
    return round(saved, 2)


def simple_search(
    transactions: list[dict[str, Any]] | pd.DataFrame, query: str
) -> list[dict[str, Any]]:
    """Ищет транзакции по подстроке в описании или категории.

    Поиск нечувствителен к регистру. Пустой запрос возвращает пустой список.
    """
    text = (query or "").strip()
    if not text:
        return []

    frame = utils.ensure_frame(transactions)
    mask = (
        frame[utils.DESCRIPTION_COLUMN].str.contains(
            text, case=False, regex=False, na=False
        )
        | frame[utils.CATEGORY_COLUMN].str.contains(
            text, case=False, regex=False, na=False
        )
    )
    return utils.to_records(frame[mask])


def phone_search(
    transactions: list[dict[str, Any]] | pd.DataFrame,
) -> list[dict[str, Any]]:
    """Возвращает транзакции, в описании которых есть мобильный номер."""
    frame = utils.ensure_frame(transactions)
    mask = frame[utils.DESCRIPTION_COLUMN].map(_matches_phone)
    return utils.to_records(frame[mask])


def transfers_to_people(
    transactions: list[dict[str, Any]] | pd.DataFrame,
) -> list[dict[str, Any]]:
    """Возвращает переводы физическим лицам («Имя Ф.»)."""
    frame = utils.ensure_frame(transactions)
    mask = (
        frame[utils.CATEGORY_COLUMN].str.casefold() == "переводы"
    ) & frame[utils.DESCRIPTION_COLUMN].str.contains(
        PERSON_PATTERN, regex=True, na=False
    )
    return utils.to_records(frame[mask])
