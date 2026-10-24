"""JSON-ответы для веб-страниц «Главная» и «События»."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from src import external_api, utils

logger = logging.getLogger(__name__)

CASHBACK_PER_RUBLES = 100.0
TOP_TRANSACTIONS_LIMIT = 5
TOP_CATEGORIES_LIMIT = 7


def get_greeting(moment: datetime) -> str:
    """Возвращает приветствие по текущему времени суток."""
    hour = moment.hour
    if 6 <= hour <= 11:
        return "Доброе утро"
    if 12 <= hour <= 17:
        return "Добрый день"
    if 18 <= hour <= 22:
        return "Добрый вечер"
    return "Доброй ночи"


def build_cards(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Считает расходы и кешбэк по каждой карте за период."""
    expenses = frame[
        (frame[utils.PAYMENT_AMOUNT_COLUMN] < 0)
        & (frame[utils.CARD_COLUMN] != "")
    ]
    if expenses.empty:
        return []

    grouped = expenses.groupby("last_digits")[utils.PAYMENT_AMOUNT_COLUMN].sum()
    cards: list[dict[str, Any]] = []
    for digits, amount in grouped.items():
        total_spent = round(abs(float(amount)), 2)
        cards.append(
            {
                "last_digits": str(digits),
                "total_spent": total_spent,
                "cashback": round(total_spent / CASHBACK_PER_RUBLES, 2),
            }
        )

    cards.sort(key=lambda card: card["total_spent"], reverse=True)
    return cards


def build_top_transactions(
    frame: pd.DataFrame, limit: int = TOP_TRANSACTIONS_LIMIT
) -> list[dict[str, Any]]:
    """Возвращает топ транзакций по сумме платежа."""
    if frame.empty:
        return []

    top = frame.sort_values(
        by=utils.PAYMENT_AMOUNT_COLUMN, ascending=False
    ).head(limit)

    result: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        result.append(
            {
                "date": utils.format_date(row[utils.DATE_COLUMN]),
                "amount": round(float(row[utils.PAYMENT_AMOUNT_COLUMN]), 2),
                "category": row[utils.CATEGORY_COLUMN],
                "description": row[utils.DESCRIPTION_COLUMN],
            }
        )
    return result


def _category_totals(frame: pd.DataFrame) -> pd.Series:
    """Суммарные траты (по модулю) по категориям, по убыванию."""
    if frame.empty:
        return pd.Series(dtype="float64")
    totals = frame.groupby(utils.CATEGORY_COLUMN)[
        utils.PAYMENT_AMOUNT_COLUMN
    ].sum()
    return totals.abs().sort_values(ascending=False)


def build_expenses(frame: pd.DataFrame) -> dict[str, Any]:
    """Формирует блок «Расходы»: основные категории и переводы/наличные."""
    expenses = frame[frame[utils.PAYMENT_AMOUNT_COLUMN] < 0]
    if expenses.empty:
        return {
            "total_amount": 0,
            "main": [],
            "transfers_and_cash": [],
        }

    total_amount = int(round(float(expenses[utils.PAYMENT_AMOUNT_COLUMN].sum())))

    transfers = expenses[
        expenses[utils.CATEGORY_COLUMN].isin(utils.TRANSFER_CATEGORIES)
    ]
    transfers_and_cash = [
        {"category": category, "amount": int(round(float(amount)))}
        for category, amount in _category_totals(transfers).items()
    ]

    main_frame = expenses[
        ~expenses[utils.CATEGORY_COLUMN].isin(utils.TRANSFER_CATEGORIES)
    ]
    totals = _category_totals(main_frame)

    main: list[dict[str, Any]] = [
        {"category": category, "amount": int(round(float(amount)))}
        for category, amount in totals.head(TOP_CATEGORIES_LIMIT).items()
    ]

    rest = totals.iloc[TOP_CATEGORIES_LIMIT:]
    if not rest.empty:
        main.append(
            {
                "category": "Остальное",
                "amount": int(round(float(rest.sum()))),
            }
        )

    return {
        "total_amount": abs(total_amount),
        "main": main,
        "transfers_and_cash": transfers_and_cash,
    }


def build_income(frame: pd.DataFrame) -> dict[str, Any]:
    """Формирует блок «Поступления»."""
    income = frame[frame[utils.PAYMENT_AMOUNT_COLUMN] > 0]
    if income.empty:
        return {"total_amount": 0, "main": []}

    total_amount = int(round(float(income[utils.PAYMENT_AMOUNT_COLUMN].sum())))
    grouped = (
        income.groupby(utils.CATEGORY_COLUMN)[utils.PAYMENT_AMOUNT_COLUMN]
        .sum()
        .sort_values(ascending=False)
    )
    main = [
        {"category": category, "amount": int(round(float(amount)))}
        for category, amount in grouped.items()
    ]
    return {"total_amount": total_amount, "main": main}


def _get_frame(
    transactions: pd.DataFrame | list[dict[str, Any]] | None,
) -> pd.DataFrame:
    if transactions is None:
        return utils.read_transactions(utils.DEFAULT_DATA_FILE)
    return utils.ensure_frame(transactions)


def main_page(
    date_time: str,
    transactions: pd.DataFrame | list[dict[str, Any]] | None = None,
    settings_path: str | None = None,
) -> dict[str, Any]:
    """Главная страница: приветствие, карты, топ-5, курсы и акции."""
    moment = utils.parse_datetime(date_time)
    frame = utils.filter_successful(_get_frame(transactions))
    start, end = utils.month_bounds(moment)
    period = utils.filter_period(frame, start, end)

    settings = utils.load_user_settings(
        settings_path or utils.DEFAULT_SETTINGS_FILE
    )

    logger.info(
        "Главная страница за %s: операций в выборке %d",
        moment.strftime("%d.%m.%Y"),
        len(period),
    )
    return {
        "greeting": get_greeting(moment),
        "cards": build_cards(period),
        "top_transactions": build_top_transactions(period),
        "currency_rates": external_api.get_currency_rates(
            list(settings["user_currencies"])
        ),
        "stock_prices": external_api.get_stock_prices(
            list(settings["user_stocks"])
        ),
    }


def events_page(
    date_time: str,
    period: str = "M",
    transactions: pd.DataFrame | list[dict[str, Any]] | None = None,
    settings_path: str | None = None,
) -> dict[str, Any]:
    """Страница «События»: расходы, поступления, курсы и акции."""
    moment = utils.parse_datetime(date_time)
    frame = utils.filter_successful(_get_frame(transactions))
    start, end = utils.get_period_bounds(frame, moment, period)
    selected = utils.filter_period(frame, start, end)

    settings = utils.load_user_settings(
        settings_path or utils.DEFAULT_SETTINGS_FILE
    )

    logger.info(
        "События за период %s - %s (%s): операций %d",
        start.strftime("%d.%m.%Y"),
        end.strftime("%d.%m.%Y"),
        period,
        len(selected),
    )
    return {
        "expenses": build_expenses(selected),
        "income": build_income(selected),
        "currency_rates": external_api.get_currency_rates(
            list(settings["user_currencies"])
        ),
        "stock_prices": external_api.get_stock_prices(
            list(settings["user_stocks"])
        ),
    }
