"""Источники цен: Wildberries по артикулу и произвольная страница по CSS-селектору."""
from __future__ import annotations

import os
import re
import time
import urllib.request
from html.parser import HTMLParser

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
            if resp.status_code == 403:
                last = SourceError("доступ запрещён (HTTP 403) — WB может блокировать IP")
            else:
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


def page_price(url: str, selector: str, timeout: float = 10.0, retries: int = 3) -> float:
    html_text = _fetch_html(url, timeout, retries)
    text = select_text(html_text, selector)
    if text is None:
        raise SourceError(f"по селектору {selector!r} ничего не найдено")
    price = parse_price(text)
    if price is None:
        raise SourceError(f"в блоке {selector!r} нет числа: {text[:80]!r}")
    return price


def _fetch_html(url: str, timeout: float, retries: int) -> str:
    if url.startswith("file://"):
        # локальные страницы — удобно для тестов и отладки селекторов
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            last = SourceError(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            last = SourceError(e.__class__.__name__)
        if attempt < retries:
            time.sleep(2 * attempt)
    raise last or SourceError("запрос не удался")


# --- разбор HTML и простые CSS-селекторы (tag, #id, .class, [attr=value], пробел = потомок) ---

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "source", "track", "wbr"}


class _Node:
    def __init__(self, tag: str, attrs: list, parent: "_Node | None"):
        self.tag = tag
        self.parent = parent
        self.children: list[_Node] = []
        self.text_parts: list[str] = []
        self.attrs = dict(attrs)
        self.classes = set(str(self.attrs.get("class", "")).split())

    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return re.sub(r"\s+", " ", " ".join(parts)).strip()


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", [], None)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].text_parts.append(data)


_SELECTOR = re.compile(
    r"""^([a-zA-Z][a-zA-Z0-9-]*)?"""                 # тег
    r"""(?:#([\w-]+))?"""                            # #id
    r"""((?:\.[\w-]+)+)?"""                          # .class.class
    r"""(?:\[([^\]=]+)=?["']?([^\]'"]*)["']?\])?$"""  # [attr=value]
)


def _compile_part(part: str) -> tuple:
    m = _SELECTOR.match(part.strip())
    if not m or not any(m.groups()):
        raise SourceError(f"не понимаю селектор: {part!r} (поддерживаются tag, #id, .class, [attr=value])")
    tag, id_, classes, attr, value = m.groups()
    return (tag.lower() if tag else None,
            id_,
            {c for c in (classes or "").lstrip(".").split(".") if c},
            attr, value)


def _matches(node: _Node, part: tuple) -> bool:
    tag, id_, classes, attr, value = part
    if tag and node.tag != tag:
        return False
    if id_ and node.attrs.get("id") != id_:
        return False
    if classes and not classes <= node.classes:
        return False
    if attr is not None and node.attrs.get(attr) != value:
        return False
    return True


def select_text(html_text: str, selector: str) -> str | None:
    """Первый блок, подходящий под селектор: последний элемент цепочки — сам блок,
    предыдущие — его предки (как в CSS)."""
    parts = [_compile_part(p) for p in selector.split()]
    builder = _TreeBuilder()
    builder.feed(html_text)
    builder.close()
    for node in _walk(builder.root):
        if not _matches(node, parts[-1]):
            continue
        ancestor, chain = node.parent, list(reversed(parts[:-1]))
        for part in chain:
            while ancestor and ancestor.tag != "#root" and not _matches(ancestor, part):
                ancestor = ancestor.parent
            if not ancestor or ancestor.tag == "#root":
                break
            ancestor = ancestor.parent
        else:
            return node.text()
    return None


def _walk(node: _Node):
    for child in node.children:
        yield child
        yield from _walk(child)


_NUMBER = re.compile(r"\d[\d\s\u00a0\u202f.,']*")


def parse_price(text: str) -> float | None:
    """«2 499,90 ₽» → 2499.9; «$1,234.56» → 1234.56; «1 999» → 1999.0."""
    m = _NUMBER.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s\u00a0\u202f']", "", m.group(0))
    if "," in raw and "." in raw:
        raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") \
            else raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = head.replace(",", "") + (f".{tail}" if 0 < len(tail) <= 2 else "")
    return float(raw) if raw else None
