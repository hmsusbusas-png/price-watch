"""Price sources. To add a shop, write a class with `kind` and `quote()` and register it in SOURCES."""
from __future__ import annotations

from collections.abc import Callable

from .base import Quote, Source, SourceError
from .page import Page
from .wildberries import Product, Wildberries

SOURCES: dict[str, Callable[[], Source]] = {
    Wildberries.kind: Wildberries,
    Page.kind: Page,
}


def make(kind: str) -> Source:
    try:
        return SOURCES[kind]()
    except KeyError:
        raise SourceError(f"неизвестный источник {kind!r}, есть: {', '.join(SOURCES)}") from None


__all__ = ["SOURCES", "Page", "Product", "Quote", "Source", "SourceError", "Wildberries", "make"]
