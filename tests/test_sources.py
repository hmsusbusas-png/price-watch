from __future__ import annotations

import pytest
import requests

from pricewatch.sources import Page, SourceError, Wildberries, make
from pricewatch.sources.base import get
from pricewatch.sources.page import parse_price, select_text
from pricewatch.sources.wildberries import parse_product

from .conftest import FIXTURES, FakeResponse, FakeSession

SHOP = (FIXTURES / "shop.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(("text", "expected"), [
    ("2 499,90 ₽", 2499.9),
    ("$1,234.56", 1234.56),
    ("1 999", 1999.0),
    ("12,50", 12.5),
    ("1,234", 1234.0),
    ("7 €", 7.0),
    ("от 3 200 руб.", 3200.0),
    ("1.234,5", 1234.5),
    ("нет в наличии", None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_selector_with_ancestor():
    assert select_text(SHOP, "div#product span.product-price") == "2 499,90 ₽"


def test_selector_by_class_reads_nested_text():
    assert select_text(SHOP, ".old-price") == "3 199,00 ₽"


def test_selector_ancestor_must_exist():
    assert select_text(SHOP, "footer span.product-price") is None


def test_bad_selector_is_explained():
    with pytest.raises(SourceError, match="не понимаю селектор"):
        select_text(SHOP, "div > span")


def test_page_quote_from_file():
    quote = Page().quote((FIXTURES / "shop.html").resolve().as_uri(), "span.product-price")
    assert quote.price == 2499.9
    assert quote.title == "Test Shop — Mechanical Keyboard K87"


def test_page_needs_selector():
    with pytest.raises(SourceError, match="селектор"):
        Page().quote("https://example.com/item")


def test_page_rejects_other_schemes():
    with pytest.raises(SourceError, match="http"):
        Page().fetch("ftp://example.com/item")


def test_parse_product_new_and_old_formats(wb_card):
    new, old, broken = (parse_product(p) for p in wb_card["data"]["products"])
    assert new.price == 549.0 and new.old_price == 1299.0 and new.discount == 58
    assert new.brand == "Kitchen Lab"
    assert old.price == 990.0 and old.old_price == 1500.0
    assert broken is None


def test_wb_quote(wb_card):
    session = FakeSession(FakeResponse(body=wb_card))
    quote = Wildberries(session=session).quote("155713071")
    assert quote.price == 549.0
    url, kwargs = session.calls[0]
    assert "card.wb.ru" in url and kwargs["params"]["nm"] == "155713071"


def test_wb_blocked_ip_is_explained():
    with pytest.raises(SourceError, match="403"):
        Wildberries(session=FakeSession(FakeResponse(403, text="blocked"))).quote("1")


def test_wb_unknown_sku():
    with pytest.raises(SourceError, match="не найден"):
        Wildberries(session=FakeSession(FakeResponse(body={"data": {"products": []}}))).quote("1")


def test_wb_sku_must_be_digits():
    with pytest.raises(SourceError, match="число"):
        Wildberries(session=FakeSession()).quote("abc")


def test_wb_search_deduplicates(wb_card):
    empty = {"data": {"products": []}}
    session = FakeSession(FakeResponse(body=wb_card), FakeResponse(body=wb_card), FakeResponse(body=empty))
    found = Wildberries(session=session).search("капучинатор", pages=3)
    assert [p.sku for p in found] == [155713071, 42]


def test_get_retries_server_errors(monkeypatch):
    monkeypatch.setattr("pricewatch.sources.base.time.sleep", lambda _: None)
    session = FakeSession(FakeResponse(502), FakeResponse(200, body={}))
    assert get(session, "https://example.com", attempts=3).status_code == 200
    assert len(session.calls) == 2


def test_get_gives_up_on_timeouts(monkeypatch):
    monkeypatch.setattr("pricewatch.sources.base.time.sleep", lambda _: None)

    class Hanging:
        def get(self, *args, **kwargs):
            raise requests.Timeout

    with pytest.raises(SourceError, match="no answer"):
        get(Hanging(), "https://example.com", attempts=2)


def test_unknown_source_kind():
    with pytest.raises(SourceError, match="неизвестный источник"):
        make("ozon")
