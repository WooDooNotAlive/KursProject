"""Тесты модуля utils."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import pytest

from src import utils


def test_prepare_transactions_parses_dates(frame: pd.DataFrame) -> None:
    assert pd.api.types.is_datetime64_any_dtype(frame[utils.DATE_COLUMN])
    assert frame[utils.DATE_COLUMN].iloc[0] == pd.Timestamp("2021-12-01 10:00:00")


def test_prepare_transactions_fills_category(raw_frame: pd.DataFrame) -> None:
    raw_frame.loc[0, utils.CATEGORY_COLUMN] = None
    prepared = utils.prepare_transactions(raw_frame)
    assert prepared[utils.CATEGORY_COLUMN].iloc[0] == utils.UNKNOWN_CATEGORY


@pytest.mark.parametrize(
    ("value", "expected"),
    [("*1111", "1111"), ("1111", "1111"), ("", ""), (None, ""), (123456, "3456")],
)
def test_last_digits(value: object, expected: str) -> None:
    assert utils.last_digits(value) == expected


def test_filter_period(frame: pd.DataFrame) -> None:
    result = utils.filter_period(
        frame, datetime(2021, 12, 1), datetime(2021, 12, 31, 23, 59)
    )
    assert len(result) == 10
    assert result[utils.DATE_COLUMN].min().month == 12


def test_filter_successful(frame: pd.DataFrame) -> None:
    result = utils.filter_successful(frame)
    assert all(result[utils.STATUS_COLUMN] == "OK")
    assert len(result) == 10


def test_month_bounds() -> None:
    start, end = utils.month_bounds(datetime(2021, 5, 20, 13, 45))
    assert start == datetime(2021, 5, 1, 0, 0)
    assert end == datetime(2021, 5, 20, 23, 59, 59, 999999)


def test_week_bounds_starts_on_monday() -> None:
    start, end = utils.week_bounds(datetime(2021, 12, 8, 10, 0))
    assert start.weekday() == 0
    assert start.date() == datetime(2021, 12, 6).date()
    assert end.day == 8


def test_year_bounds() -> None:
    start, _ = utils.year_bounds(datetime(2021, 12, 8, 10, 0))
    assert (start.month, start.day) == (1, 1)


def test_get_period_bounds_all(frame: pd.DataFrame) -> None:
    start, end = utils.get_period_bounds(
        frame, datetime(2021, 12, 10), "ALL"
    )
    assert start == datetime(2021, 11, 20, 10, 0)
    assert end.day == 10


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2021-12-31 16:44:00", datetime(2021, 12, 31, 16, 44)),
        ("2021-12-31T16:44:00", datetime(2021, 12, 31, 16, 44)),
        ("2021-12-31", datetime(2021, 12, 31)),
        ("31.12.2021", datetime(2021, 12, 31)),
    ],
)
def test_parse_datetime(value: str, expected: datetime) -> None:
    assert utils.parse_datetime(value) == expected


def test_parse_datetime_invalid() -> None:
    with pytest.raises(ValueError):
        utils.parse_datetime("не дата")


def test_load_user_settings_defaults(tmp_path: object) -> None:
    settings = utils.load_user_settings(tmp_path / "missing.json")  # type: ignore[operator]
    assert settings["user_currencies"] == ["USD", "EUR"]
    assert "AAPL" in settings["user_stocks"]


def test_load_user_settings_from_file(settings_file: str) -> None:
    settings = utils.load_user_settings(settings_file)
    assert settings["user_stocks"] == ["AAPL", "TSLA"]


def test_to_records_json_serializable(frame: pd.DataFrame) -> None:
    records = utils.to_records(frame)
    assert len(records) == 11
    assert records[0]["card"] == "1111"
    assert records[0]["date"] == "01.12.2021"
    json.dumps(records, ensure_ascii=False)


def test_read_transactions_real_file() -> None:
    if not utils.DEFAULT_DATA_FILE.exists():
        pytest.skip("Нет файла с данными")
    frame = utils.read_transactions(utils.DEFAULT_DATA_FILE)
    assert len(frame) > 1000
    assert pd.api.types.is_datetime64_any_dtype(frame[utils.DATE_COLUMN])


def test_read_transactions_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        utils.read_transactions("нет_такого_файла.xlsx")
