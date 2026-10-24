"""Тесты отчётов и декоратора сохранения."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src import reports


@pytest.fixture(autouse=True)
def _reports_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Перенаправляет отчёты по умолчанию во временную папку."""
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path)
    return tmp_path


def test_spending_by_category(frame: pd.DataFrame) -> None:
    result = reports.spending_by_category(
        frame, "Супермаркеты", "2021-12-31"
    )

    assert list(result.columns) == list(reports.REPORT_COLUMNS)
    assert len(result) == 2
    assert result["Сумма"].sum() == pytest.approx(1700.0)
    assert set(result["Сумма"]) == {700.0, 1000.0}


def test_spending_by_category_case_insensitive(frame: pd.DataFrame) -> None:
    result = reports.spending_by_category(
        frame, "супермаркеты", "2021-12-31"
    )
    assert len(result) == 2


def test_spending_by_category_unknown(frame: pd.DataFrame) -> None:
    result = reports.spending_by_category(frame, "Нет такой", "2021-12-31")
    assert result.empty
    assert list(result.columns) == list(reports.REPORT_COLUMNS)


def test_spending_by_weekday(frame: pd.DataFrame) -> None:
    result = reports.spending_by_weekday(frame, "2021-12-31")

    assert list(result.columns) == ["День недели", "Средние траты"]
    assert len(result) == 7
    assert result["День недели"].tolist() == list(reports.WEEKDAYS)


def test_spending_by_workday(frame: pd.DataFrame) -> None:
    result = reports.spending_by_workday(frame, "2021-12-31")

    assert list(result.columns) == ["Тип дня", "Средние траты"]
    assert set(result["Тип дня"]) == {"Рабочий день", "Выходной день"}


def test_report_decorator_default_name(_reports_dir: Path) -> None:
    @reports.report
    def dummy() -> pd.DataFrame:
        return pd.DataFrame({"a": [1, 2]})

    result = dummy()
    files = list(_reports_dir.glob("dummy_*.csv"))

    assert len(result) == 2
    assert len(files) == 1
    assert files[0].exists()


def test_report_decorator_with_filename(
    _reports_dir: Path, tmp_path: Path
) -> None:
    target = tmp_path / "custom.csv"

    @reports.report(str(target))
    def dummy() -> pd.DataFrame:
        return pd.DataFrame({"a": [1]})

    dummy()
    assert target.exists()
    assert "a" in target.read_text(encoding="utf-8-sig")


def test_report_decorator_saves_json(tmp_path: Path) -> None:
    target = tmp_path / "payload.json"

    @reports.report(str(target))
    def dummy() -> dict[str, Any]:
        return {"key": "значение"}

    dummy()
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "key": "значение"
    }


def test_report_decorator_returns_result_unchanged() -> None:
    @reports.report
    def dummy(value: int) -> int:
        return value * 2

    assert dummy(21) == 42
    assert dummy.__name__ == "dummy"
