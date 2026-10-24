"""Тесты веб-страниц (JSON-ответов)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import pytest

from src import utils, views


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (5, "Доброй ночи"),
        (6, "Доброе утро"),
        (11, "Доброе утро"),
        (12, "Добрый день"),
        (17, "Добрый день"),
        (18, "Добрый вечер"),
        (22, "Добрый вечер"),
        (23, "Доброй ночи"),
        (0, "Доброй ночи"),
    ],
)
def test_get_greeting(hour: int, expected: str) -> None:
    assert views.get_greeting(datetime(2021, 12, 1, hour)) == expected


def test_build_cards(frame: pd.DataFrame) -> None:
    period = utils.filter_period(
        utils.filter_successful(frame),
        datetime(2021, 12, 1),
        datetime(2021, 12, 31, 23, 59),
    )
    cards = views.build_cards(period)

    assert [card["last_digits"] for card in cards] == ["1111", "2222"]
    assert cards[0]["total_spent"] == pytest.approx(2050.0)
    assert cards[0]["cashback"] == pytest.approx(20.5)
    assert cards[1]["total_spent"] == pytest.approx(300.0)
    assert cards[1]["cashback"] == pytest.approx(3.0)


def test_build_cards_empty() -> None:
    empty = pd.DataFrame(
        {
            utils.CARD_COLUMN: [],
            utils.PAYMENT_AMOUNT_COLUMN: [],
            "last_digits": [],
        }
    )
    assert views.build_cards(empty) == []


def test_build_top_transactions_sorted(frame: pd.DataFrame) -> None:
    period = utils.filter_successful(frame)
    top = views.build_top_transactions(period, limit=3)

    assert len(top) == 3
    amounts = [item["amount"] for item in top]
    assert amounts == sorted(amounts, reverse=True)
    assert top[0]["amount"] == 5000
    assert set(top[0]) == {"date", "amount", "category", "description"}


def test_build_expenses(frame: pd.DataFrame) -> None:
    period = utils.filter_period(
        utils.filter_successful(frame),
        datetime(2021, 12, 1),
        datetime(2021, 12, 31, 23, 59),
    )
    expenses = views.build_expenses(period)

    assert expenses["total_amount"] == 4350
    assert expenses["transfers_and_cash"] == [
        {"category": "Переводы", "amount": 2000},
        {"category": "Наличные", "amount": 300},
    ]
    categories = [item["category"] for item in expenses["main"]]
    assert "Переводы" not in categories
    assert "Наличные" not in categories
    main_amounts = [item["amount"] for item in expenses["main"]]
    assert main_amounts == sorted(main_amounts, reverse=True)


def test_build_expenses_top_seven_and_rest() -> None:
    rows = []
    for index in range(9):
        rows.append(
            {
                utils.DATE_COLUMN: f"0{index % 9 + 1}.12.2021 10:00:00",
                utils.PAYMENT_AMOUNT_COLUMN: -(index + 1) * 100,
                utils.CATEGORY_COLUMN: f"Категория {index + 1}",
                utils.DESCRIPTION_COLUMN: "тест",
                utils.STATUS_COLUMN: "OK",
                utils.CARD_COLUMN: "*1111",
            }
        )
    frame = utils.prepare_transactions(pd.DataFrame(rows))

    expenses = views.build_expenses(frame)

    assert len(expenses["main"]) == 8
    assert expenses["main"][0] == {"category": "Категория 9", "amount": 900}
    assert expenses["main"][-1] == {"category": "Остальное", "amount": 300}
    assert expenses["total_amount"] == 4500


def test_build_income(frame: pd.DataFrame) -> None:
    income = views.build_income(frame)
    assert income["total_amount"] == 5000
    assert income["main"][0] == {"category": "Пополнения", "amount": 5000}


def test_main_page(
    frame: pd.DataFrame,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.views.external_api.get_currency_rates",
        lambda currencies, **_: [{"currency": c, "rate": 75.0} for c in currencies],
    )
    monkeypatch.setattr(
        "src.views.external_api.get_stock_prices",
        lambda stocks, **_: [{"stock": s, "price": 100.0} for s in stocks],
    )

    payload = views.main_page(
        "2021-12-31 16:44:00", frame, settings_path=settings_file
    )

    assert payload["greeting"] == "Добрый день"
    assert len(payload["top_transactions"]) == 5
    assert payload["currency_rates"] == [
        {"currency": "USD", "rate": 75.0},
        {"currency": "EUR", "rate": 75.0},
    ]
    assert payload["stock_prices"] == [
        {"stock": "AAPL", "price": 100.0},
        {"stock": "TSLA", "price": 100.0},
    ]
    assert set(payload) == {
        "greeting",
        "cards",
        "top_transactions",
        "currency_rates",
        "stock_prices",
    }


def test_main_page_uses_only_current_month(
    frame: pd.DataFrame,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.views.external_api.get_currency_rates", lambda *_, **__: []
    )
    monkeypatch.setattr(
        "src.views.external_api.get_stock_prices", lambda *_, **__: []
    )

    payload = views.main_page(
        "2021-12-31 10:00:00", frame, settings_path=settings_file
    )
    amount = sum(card["total_spent"] for card in payload["cards"])
    assert amount == pytest.approx(2350.0)


def test_events_page(
    frame: pd.DataFrame,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.views.external_api.get_currency_rates", lambda *_, **__: []
    )
    monkeypatch.setattr(
        "src.views.external_api.get_stock_prices", lambda *_, **__: []
    )

    payload = views.events_page(
        "2021-12-31 10:00:00", "M", frame, settings_path=settings_file
    )

    assert set(payload) == {
        "expenses",
        "income",
        "currency_rates",
        "stock_prices",
    }
    assert payload["expenses"]["total_amount"] == 4350
    assert payload["income"]["total_amount"] == 5000


def test_events_page_periods(
    frame: pd.DataFrame,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.views.external_api.get_currency_rates", lambda *_, **__: []
    )
    monkeypatch.setattr(
        "src.views.external_api.get_stock_prices", lambda *_, **__: []
    )
    for period in ("W", "M", "Y", "ALL"):
        payload = views.events_page(
            "2021-12-10 10:00:00", period, frame, settings_path=settings_file
        )
        assert payload["expenses"]["total_amount"] >= 0


def test_events_all_period_includes_november(
    frame: pd.DataFrame,
    settings_file: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.views.external_api.get_currency_rates", lambda *_, **__: []
    )
    monkeypatch.setattr(
        "src.views.external_api.get_stock_prices", lambda *_, **__: []
    )
    payload: dict[str, Any] = views.events_page(
        "2021-12-10 10:00:00", "ALL", frame, settings_path=settings_file
    )
    assert payload["expenses"]["total_amount"] == 4350 + 700
