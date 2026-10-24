"""Тесты клиента внешних API (без реальных запросов)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from src import external_api


class FakeResponse:
    """Минимальная заглушка ответа requests."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Изолирует файл кеша и убирает паузы между повторами."""
    cache_file = tmp_path / "api_cache.json"
    monkeypatch.setattr(external_api, "CACHE_FILE", cache_file)
    monkeypatch.setattr(external_api.time, "sleep", lambda *_: None)
    return cache_file


def test_get_currency_rates_from_cbr(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "Valute": {
            "USD": {"Value": 73.21, "Nominal": 1},
            "EUR": {"Value": 87.08, "Nominal": 1},
        }
    }
    monkeypatch.setattr(
        external_api.requests, "get", lambda *a, **k: FakeResponse(payload)
    )

    rates = external_api.get_currency_rates(["USD", "EUR"])

    assert rates == [
        {"currency": "USD", "rate": 73.21},
        {"currency": "EUR", "rate": 87.08},
    ]


def test_get_currency_rates_uses_nominal(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"Valute": {"JPY": {"Value": 50.0, "Nominal": 100}}}
    monkeypatch.setattr(
        external_api.requests, "get", lambda *a, **k: FakeResponse(payload)
    )

    rates = external_api.get_currency_rates(["JPY"])
    assert rates[0]["rate"] == 0.5


def test_get_currency_rates_fallback_to_er_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    er_payload = {"result": "success", "rates": {"USD": 0.0125, "EUR": 0.011}}

    def fake_get(url: str, **kwargs: Any) -> Any:
        if url == external_api.CBR_URL:
            return FakeResponse(ValueError("битый ответ ЦБ"))
        return FakeResponse(er_payload)

    monkeypatch.setattr(external_api.requests, "get", fake_get)

    rates = external_api.get_currency_rates(["USD"])
    assert rates[0]["rate"] == pytest.approx(80.0)


def test_get_currency_rates_handles_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> Any:
        raise requests.ConnectionError("нет сети")

    monkeypatch.setattr(external_api.requests, "get", fake_get)

    rates = external_api.get_currency_rates(["USD", "EUR"])
    assert rates == [
        {"currency": "USD", "rate": 0.0},
        {"currency": "EUR", "rate": 0.0},
    ]


def test_get_currency_rates_uses_cache(
    monkeypatch: pytest.MonkeyPatch, _cache: Path
) -> None:
    external_api._cache_set("currency_rates", {"USD": 90.0})

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("запрос не должен выполняться")

    monkeypatch.setattr(external_api.requests, "get", fake_get)
    rates = external_api.get_currency_rates(["USD"])
    assert rates == [{"currency": "USD", "rate": 90.0}]


def test_get_stock_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "chart": {"result": [{"meta": {"regularMarketPrice": 150.123}}]}
    }
    monkeypatch.setattr(
        external_api.requests, "get", lambda *a, **k: FakeResponse(payload)
    )

    prices = external_api.get_stock_prices(["AAPL", "TSLA"])
    assert prices == [
        {"stock": "AAPL", "price": 150.12},
        {"stock": "TSLA", "price": 150.12},
    ]


def test_get_stock_prices_handles_bad_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        external_api.requests,
        "get",
        lambda *a, **k: FakeResponse({"chart": {"result": []}}),
    )

    prices = external_api.get_stock_prices(["AAPL"])
    assert prices == [{"stock": "AAPL", "price": 0.0}]


def test_get_stock_prices_falls_back_to_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_api._cache_set("stock_prices", {"AAPL": 111.11})

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        raise requests.Timeout("таймаут")

    monkeypatch.setattr(external_api.requests, "get", fake_get)
    prices = external_api.get_stock_prices(["AAPL"])
    assert prices == [{"stock": "AAPL", "price": 111.11}]


def test_get_json_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.ConnectionError("сбой")
        return FakeResponse({"ok": True})

    monkeypatch.setattr(external_api.requests, "get", fake_get)
    assert external_api._get_json("https://example.com") == {"ok": True}
    assert calls["count"] == 2


def test_get_json_returns_none_after_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        external_api.requests,
        "get",
        lambda *a, **k: FakeResponse(ValueError("битый json")),
    )
    assert external_api._get_json("https://example.com") is None


def test_cache_ttl(monkeypatch: pytest.MonkeyPatch, _cache: Path) -> None:
    _cache.write_text(
        json.dumps({"currency_rates": {"timestamp": 0, "value": {"USD": 1}}}),
        encoding="utf-8",
    )
    assert external_api._cache_get("currency_rates") is None


def test_cache_corrupted_file(_cache: Path) -> None:
    _cache.write_text("не json", encoding="utf-8")
    assert external_api._load_cache() == {}


def test_cache_save_error_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_mkdir(*args: Any, **kwargs: Any) -> None:
        raise OSError("нет прав")

    monkeypatch.setattr(external_api.Path, "mkdir", broken_mkdir)
    external_api._save_cache({"key": "value"})


def test_get_currency_rates_with_rub(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"Valute": {"USD": {"Value": 70.0, "Nominal": 1}}}
    monkeypatch.setattr(
        external_api.requests, "get", lambda *a, **k: FakeResponse(payload)
    )
    rates = external_api.get_currency_rates(["RUB"])
    assert rates == [{"currency": "RUB", "rate": 1.0}]
