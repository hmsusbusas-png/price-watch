"""Источники цен: Wildberries по артикулу и произвольная страница по CSS-селектору."""
from __future__ import annotations

import os
import time

import requests

WB_CARD_URL = os.environ.get("WB_API_BASE", "https://card.wb.ru/cards/v2/detail")
# dest=-1257786 — Москва; без него карточный эндпоинт отдаёт пустой список
WB_PARAMS = {"appType": "1", "curr": "rub", "dest": "-1257786", "spp": "30"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class SourceError(Exception):
    """Сеть, таймаут, неожиданный ответ или не удалось вытащить цену."""


def fetch_price(item: dict, timeout: float = 10.0, retries: int = 3) -> float:
    if item.get("type") == "wb":
        return wb_price(item["sku"], timeout=timeout, retries=retries)
    if item.get("type") == "url":
        return page_price(item["url"], item["selector"], timeout=timeout, retries=retries)
    raise SourceError(f"неизвестный тип источника: {item.get('type')!r}")


def _get_json(url: str, params: dict, timeout: float, retries: int) -> dict:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            last = SourceError(f"HTTP {resp.status_code}")
        except (requests.RequestException, ValueError) as e:
            last = SourceError(e.__class__.__name__)
        if attempt < retries:
            time.sleep(2 * attempt)
    raise last or SourceError("запрос не удался")


def wb_price(sku: str, timeout: float = 10.0, retries: int = 3) -> float:
    """Цена со скидкой из публичного карточного API WB; цены приходят в копейках."""
    data = _get_json(WB_CARD_URL, {**WB_PARAMS, "nm": str(sku)}, timeout, retries)
    products = (data.get("data") or {}).get("products") or []
    if not products:
        raise SourceError(f"товар {sku} не найден — проверьте артикул")
    for size in products[0].get("sizes") or []:
        price = size.get("price") or {}
        if price.get("product"):
            return round(price["product"] / 100, 2)
    raise SourceError(f"у товара {sku} сейчас нет цены")
