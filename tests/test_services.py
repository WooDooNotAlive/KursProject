"""Тесты сервисов."""

from __future__ import annotations

import pandas as pd
import pytest

from src import services, utils


def test_cashback_categories(frame: pd.DataFrame) -> None:
    result = services.cashback_categories(frame, 2021, 12)

    assert result["Супермаркеты"] == 10
    assert result["Фастфуд"] == 5
    assert "Переводы" not in result
    assert "Наличные" not in result
    values = list(result.values())
    assert values == sorted(values, reverse=True)


def test_cashback_categories_respects_month(frame: pd.DataFrame) -> None:
    assert services.cashback_categories(frame, 2021, 11) == {
        "Супермаркеты": 7
    }


def test_cashback_categories_bad_month(frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        services.cashback_categories(frame, 2021, 13)


def test_investment_bank(frame: pd.DataFrame) -> None:
    result = services.investment_bank("2021-12", frame, 100)
    assert result == pytest.approx(50.0)


def test_investment_bank_empty_month(frame: pd.DataFrame) -> None:
    assert services.investment_bank("2020-01", frame, 50) == 0.0


def test_investment_bank_bad_limit(frame: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        services.investment_bank("2021-12", frame, 0)


def test_investment_bank_accepts_list_of_dicts(raw_frame: pd.DataFrame) -> None:
    data = raw_frame[
        [utils.DATE_COLUMN, utils.AMOUNT_COLUMN, utils.STATUS_COLUMN]
    ].to_dict(orient="records")
    result = services.investment_bank("2021-12", data, 50)
    assert result >= 0


def test_simple_search_case_insensitive(frame: pd.DataFrame) -> None:
    lower = services.simple_search(frame, "магнит")
    upper = services.simple_search(frame, "МАГНИТ")
    assert len(lower) == 2
    assert lower == upper


def test_simple_search_by_category(frame: pd.DataFrame) -> None:
    result = services.simple_search(frame, "связь")
    assert len(result) == 4
    assert all(item["category"] == "Связь" for item in result)


def test_simple_search_empty_query(frame: pd.DataFrame) -> None:
    assert services.simple_search(frame, "") == []
    assert services.simple_search(frame, "   ") == []


def test_simple_search_no_matches(frame: pd.DataFrame) -> None:
    assert services.simple_search(frame, "такого-нет") == []


def test_phone_search_all_formats(frame: pd.DataFrame) -> None:
    result = services.phone_search(frame)
    descriptions = [item["description"] for item in result]

    assert len(result) == 4
    assert "Я МТС +7 921 11-22-33" in descriptions
    assert "Тинькофф Мобайл +7 995 555-55-55" in descriptions
    assert "МТС Mobile +7 981 333-44-55" in descriptions
    assert "Оплата 89000000000" in descriptions


@pytest.mark.parametrize(
    "text",
    [
        "+7 (900) 000-00-00",
        "8 (900) 000-00-00",
        "+7 900 000 00 00",
        "89000000000",
        "+79000000000",
        "8-900-000-00-00",
    ],
)
def test_phone_pattern_matches(text: str) -> None:
    assert services._matches_phone(f"Оплата {text}") is True


@pytest.mark.parametrize(
    "text",
    ["Заказ 12345", "31.12.2021", "Итого 1000 рублей", "8 800", "text"],
)
def test_phone_pattern_ignores_non_phones(text: str) -> None:
    assert services._matches_phone(text) is False


def test_transfers_to_people(frame: pd.DataFrame) -> None:
    result = services.transfers_to_people(frame)
    assert len(result) == 1
    assert result[0]["description"] == "Валерий А."
    assert result[0]["category"] == "Переводы"


def test_transfers_to_people_ignores_organisations() -> None:
    rows = [
        {
            utils.DATE_COLUMN: "01.12.2021 10:00:00",
            utils.PAYMENT_AMOUNT_COLUMN: -100,
            utils.CATEGORY_COLUMN: "Переводы",
            utils.DESCRIPTION_COLUMN: "ООО Ромашка",
            utils.STATUS_COLUMN: "OK",
            utils.CARD_COLUMN: "",
        },
        {
            utils.DATE_COLUMN: "02.12.2021 10:00:00",
            utils.PAYMENT_AMOUNT_COLUMN: -200,
            utils.CATEGORY_COLUMN: "Переводы",
            utils.DESCRIPTION_COLUMN: "Сергей З.",
            utils.STATUS_COLUMN: "OK",
            utils.CARD_COLUMN: "",
        },
    ]
    frame = utils.prepare_transactions(pd.DataFrame(rows))
    result = services.transfers_to_people(frame)
    assert [item["description"] for item in result] == ["Сергей З."]
