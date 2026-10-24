"""Клиент для получения курсов валют и цен на акции.

Источники:
* курсы — API Центробанка РФ (https://www.cbr-xml-daily.ru), резерв —
  exchangerate-api (https://open.er-api.com);
* акции — Yahoo Finance, резервный узел query2.

Любая ошибка сети не «роняет» приложение: данные берутся из кеша, а если
кеша нет — возвращается нулевое значение и пишется предупреждение в лог.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = PROJECT_ROOT / "data" / "cache" / "api_cache.json"
CACHE_TTL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = 10
RETRIES = 2

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
ER_API_URL = "https://open.er-api.com/v6/latest/RUB"
YAHOO_URL = "https://query{n}.finance.yahoo.com/v8/finance/chart/{ticker}"


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Кеш API повреждён или недоступен: %s", error)
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False, indent=2)
    except OSError as error:
        logger.warning("Не удалось сохранить кеш API: %s", error)


def _cache_get(key: str) -> Any:
    cached = _load_cache().get(key)
    if not cached:
        return None
    if time.time() - float(cached.get("timestamp", 0)) > CACHE_TTL_SECONDS:
        logger.info("Кеш для %s устарел", key)
        return None
    return cached.get("value")


def _cache_set(key: str, value: Any) -> None:
    cache = _load_cache()
    cache[key] = {"timestamp": time.time(), "value": value}
    _save_cache(cache)


def _get_json(url: str, *, params: dict[str, Any] | None = None) -> Any:
    """GET-запрос с повторами; возвращает None, если все попытки неудачны."""
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "bankwidget/1.0"},
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "Попытка %d/%d запроса %s не удалась: %s",
                attempt,
                RETRIES,
                url,
                error,
            )
            time.sleep(0.3 * attempt)

    logger.error("Не удалось получить данные из %s: %s", url, last_error)
    return None


def _rates_from_cbr() -> dict[str, float]:
    payload = _get_json(CBR_URL)
    if not isinstance(payload, dict):
        return {}

    rates: dict[str, float] = {}
    for code, info in (payload.get("Valute") or {}).items():
        try:
            nominal = float(info.get("Nominal") or 1) or 1.0
            rates[code] = round(float(info["Value"]) / nominal, 4)
        except (KeyError, TypeError, ValueError):
            continue
    rates["RUB"] = 1.0
    return rates


def _rates_from_er_api() -> dict[str, float]:
    payload = _get_json(ER_API_URL)
    if not isinstance(payload, dict) or payload.get("result") != "success":
        return {}

    rates: dict[str, float] = {"RUB": 1.0}
    for code, value in (payload.get("rates") or {}).items():
        try:
            rate = 1.0 / float(value)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        rates[code] = round(rate, 4)
    return rates


def get_currency_rates(
    currencies: list[str], *, use_cache: bool = True
) -> list[dict[str, Any]]:
    """Возвращает курсы валют к рублю: [{'currency': 'USD', 'rate': 73.21}]."""
    wanted = [code.upper() for code in currencies]
    cache_key = "currency_rates"
    rates: dict[str, float] = {}

    if use_cache:
        cached = _cache_get(cache_key)
        if isinstance(cached, dict):
            rates = {str(k): float(v) for k, v in cached.items()}

    if not all(code in rates and rates[code] > 0 for code in wanted):
        fresh = _rates_from_cbr() or _rates_from_er_api()
        if fresh:
            rates.update(fresh)
            if use_cache:
                _cache_set(cache_key, rates)

    result: list[dict[str, Any]] = []
    for code in wanted:
        rate = float(rates.get(code) or 0.0)
        if rate <= 0:
            logger.warning("Не удалось получить курс для %s", code)
        result.append({"currency": code, "rate": round(rate, 2)})
    return result


def _stock_price_from_yahoo(ticker: str) -> float | None:
    for host in (1, 2):
        payload = _get_json(YAHOO_URL.format(n=host, ticker=ticker))
        if not isinstance(payload, dict):
            continue
        try:
            meta = payload["chart"]["result"][0]["meta"]
            price = float(meta["regularMarketPrice"])
        except (KeyError, IndexError, TypeError, ValueError):
            logger.warning("Некорректный ответ Yahoo для %s", ticker)
            continue
        if price > 0:
            return round(price, 2)
    return None


def get_stock_prices(
    stocks: list[str], *, use_cache: bool = True
) -> list[dict[str, Any]]:
    """Возвращает цены акций: [{'stock': 'AAPL', 'price': 150.12}]."""
    cache_key = "stock_prices"
    cached: dict[str, float] = {}
    if use_cache:
        raw = _cache_get(cache_key)
        if isinstance(raw, dict):
            cached = {str(k): float(v) for k, v in raw.items()}

    result: list[dict[str, Any]] = []
    updated = False
    for ticker in (item.upper() for item in stocks):
        price = cached.get(ticker)
        if not price or price <= 0:
            price = _stock_price_from_yahoo(ticker)
            if price:
                cached[ticker] = price
                updated = True
        if not price:
            logger.warning("Не удалось получить цену акции %s", ticker)
            price = 0.0
        result.append({"stock": ticker, "price": round(float(price), 2)})

    if updated and use_cache:
        _cache_set(cache_key, cached)
    return result
