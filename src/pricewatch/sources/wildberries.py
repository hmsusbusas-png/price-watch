from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .base import Quote, SourceError, get

CARD_URL = "https://card.wb.ru/cards/v2/detail"
SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v5/search"
# dest is a delivery region; without it the API answers with an empty product list. -1257786 is Moscow.
REGION = {"appType": "1", "curr": "rub", "dest": "-1257786"}


@dataclass(frozen=True)
class Product:
    sku: int
    title: str
    brand: str
    price: float
    old_price: float
    rating: float
    reviews: int

    @property
    def url(self) -> str:
        return f"https://www.wildberries.ru/catalog/{self.sku}/detail.aspx"

    @property
    def discount(self) -> int:
        return round((1 - self.price / self.old_price) * 100) if self.old_price else 0


def _rub(kopecks: Any) -> float:
    return round(float(kopecks) / 100, 2)


def parse_product(raw: dict[str, Any]) -> Product | None:
    """One product from card or search JSON. Prices live in sizes[].price since 2024; older answers had salePriceU."""
    try:
        sku = int(raw["id"])
    except (KeyError, TypeError, ValueError):
        return None
    price = old = 0.0
    for size in raw.get("sizes") or []:
        p = size.get("price") if isinstance(size, dict) else None
        if isinstance(p, dict) and p.get("product"):
            price, old = _rub(p["product"]), _rub(p.get("basic") or p["product"])
            break
    else:
        if raw.get("salePriceU"):
            price, old = _rub(raw["salePriceU"]), _rub(raw.get("priceU") or raw["salePriceU"])
    return Product(
        sku=sku,
        title=str(raw.get("name") or f"Товар {sku}"),
        brand=str(raw.get("brand") or "").strip(),
        price=price,
        old_price=old,
        rating=float(raw.get("reviewRating") or raw.get("rating") or 0),
        reviews=int(raw.get("feedbacks") or 0),
    )


def _products(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    items = data.get("products") if isinstance(data, dict) else None
    return [p for p in items or [] if isinstance(p, dict)]


def _json(resp: requests.Response) -> Any:
    if resp.status_code == 403:
        raise SourceError("Wildberries ответил 403: обычно так блокируют зарубежные IP, попробуйте без VPN")
    if resp.status_code != 200:
        raise SourceError(f"Wildberries ответил HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError("Wildberries прислал не JSON, похоже на страницу проверки") from exc


class Wildberries:
    kind = "wb"

    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def products(self, skus: list[int]) -> list[Product]:
        if not skus:
            return []
        params = {**REGION, "spp": "30", "nm": ";".join(map(str, skus))}
        payload = _json(get(self.session, CARD_URL, params=params, timeout=self.timeout))
        return [p for p in map(parse_product, _products(payload)) if p]

    def quote(self, target: str, selector: str | None = None) -> Quote:
        if not target.isdigit():
            raise SourceError(f"артикул Wildberries должен быть числом: {target!r}")
        found = self.products([int(target)])
        if not found:
            raise SourceError(f"товар {target} не найден, проверьте артикул")
        product = found[0]
        if product.price <= 0:
            raise SourceError(f"у товара {target} сейчас нет цены, возможно его нет в наличии")
        return Quote(price=product.price, title=product.title, old_price=product.old_price or None)

    def search(self, query: str, pages: int = 1) -> list[Product]:
        seen: dict[int, Product] = {}
        for page in range(1, pages + 1):
            params = {**REGION, "query": query, "resultset": "catalog", "page": str(page), "sort": "popular"}
            items = _products(_json(get(self.session, SEARCH_URL, params=params, timeout=self.timeout)))
            if not items:
                break
            for product in filter(None, map(parse_product, items)):
                seen.setdefault(product.sku, product)
        return list(seen.values())
