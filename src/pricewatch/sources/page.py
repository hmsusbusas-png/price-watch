from __future__ import annotations

import re
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .base import Quote, SourceError, get

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# tag, #id, .class.class and [attr=value]; a space means "descendant of"
SELECTOR_PART = re.compile(
    r"^([a-zA-Z][a-zA-Z0-9-]*)?(?:#([\w-]+))?((?:\.[\w-]+)+)?(?:\[([^\]=]+)=?[\"']?([^\]'\"]*)[\"']?\])?$"
)
NUMBER = re.compile(r"\d[\d\s  .,']*")


class Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]], parent: Node | None) -> None:
        self.tag = tag
        self.parent = parent
        self.children: list[Node] = []
        self.texts: list[str] = []
        self.attrs = {k: v or "" for k, v in attrs}
        self.classes = set(self.attrs.get("class", "").split())

    def text(self) -> str:
        parts = self.texts + [child.text() for child in self.children]
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def walk(self) -> Iterator[Node]:
        for child in self.children:
            yield child
            yield from child.walk()


class TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", [], None)
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].texts.append(data)


Part = tuple[str | None, str | None, set[str], str | None, str | None]


def compile_part(part: str) -> Part:
    m = SELECTOR_PART.match(part.strip())
    if not m or not any(m.groups()):
        raise SourceError(f"не понимаю селектор {part!r}: поддерживаются tag, #id, .class и [attr=value]")
    tag, id_, classes, attr, value = m.groups()
    return (tag.lower() if tag else None, id_, {c for c in (classes or "").split(".") if c}, attr, value)


def matches(node: Node, part: Part) -> bool:
    tag, id_, classes, attr, value = part
    return ((not tag or node.tag == tag)
            and (not id_ or node.attrs.get("id") == id_)
            and classes <= node.classes
            and (attr is None or node.attrs.get(attr) == value))


def select_text(html: str, selector: str) -> str | None:
    """Text of the first element matching the selector; every part but the last must be an ancestor."""
    parts = [compile_part(p) for p in selector.split()]
    builder = TreeBuilder()
    builder.feed(html)
    builder.close()
    for node in builder.root.walk():
        if not matches(node, parts[-1]):
            continue
        ancestor = node.parent
        for part in reversed(parts[:-1]):
            while ancestor is not None and ancestor.tag != "#root" and not matches(ancestor, part):
                ancestor = ancestor.parent
            if ancestor is None or ancestor.tag == "#root":
                break
            ancestor = ancestor.parent
        else:
            return node.text()
    return None


def parse_price(text: str) -> float | None:
    """'2 499,90 ₽' -> 2499.9, '$1,234.56' -> 1234.56, '1 999' -> 1999.0."""
    m = NUMBER.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s  ']", "", m.group(0)).rstrip(".,")
    if "," in raw and "." in raw:
        raw = raw.replace(",", "") if raw.rfind(".") > raw.rfind(",") else raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = head.replace(",", "") + (f".{tail}" if len(tail) <= 2 else tail)
    return float(raw) if raw else None


def title_of(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


class Page:
    kind = "url"

    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            path = unquote(parsed.path)
            # file:///C:/shop.html has the drive letter after the slash
            return Path(path.lstrip("/") if ":" in path else path).read_text(encoding="utf-8")
        if parsed.scheme not in ("http", "https"):
            raise SourceError(f"адрес должен начинаться с http:// или https://, а не {url!r}")
        resp = get(self.session, url, timeout=self.timeout)
        if resp.status_code != 200:
            raise SourceError(f"{url} ответил HTTP {resp.status_code}")
        return resp.text

    def quote(self, target: str, selector: str | None = None) -> Quote:
        if not selector:
            raise SourceError("для страницы нужен CSS-селектор блока с ценой")
        html = self.fetch(target)
        text = select_text(html, selector)
        if text is None:
            raise SourceError(f"на странице нет элемента {selector!r}")
        price = parse_price(text)
        if price is None:
            raise SourceError(f"в {selector!r} нет числа: {text[:60]!r}")
        return Quote(price=price, title=title_of(html))
