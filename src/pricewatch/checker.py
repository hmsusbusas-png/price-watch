from __future__ import annotations

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass

from .sources import Source, SourceError, make
from .storage import Item, Store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Change:
    item: Item
    before: float | None
    after: float

    @property
    def percent(self) -> float:
        return (self.after - self.before) / self.before * 100 if self.before else 0.0


@dataclass
class Result:
    changes: list[Change]
    failed: list[tuple[Item, str]]


def money(value: float) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text.removesuffix(",00")


def check(store: Store, items: list[Item] | None = None,
          source_for: Callable[[str], Source] = make) -> Result:
    """Fetch every item once, store the price when it changed and return what changed."""
    result = Result([], [])
    sources: dict[str, Source] = {}
    for item in items if items is not None else store.items():
        try:
            source = sources.setdefault(item.kind, source_for(item.kind))
            quote = source.quote(item.target, item.selector)
        except SourceError as exc:
            log.warning("%s: %s", item.name, exc)
            result.failed.append((item, str(exc)))
            continue
        before = store.last_price(item.id)
        if before == quote.price:
            log.info("%s: без изменений, %s ₽", item.name, money(quote.price))
            continue
        store.record(item.id, quote.price)
        result.changes.append(Change(item, before, quote.price))
        log.info("%s: %s → %s ₽", item.name, "нет данных" if before is None else money(before), money(quote.price))
    return result


def alerts(changes: list[Change], drop_percent: float) -> list[str]:
    """Telegram messages for prices that went down by at least drop_percent. First records are not alerts."""
    messages = []
    for c in changes:
        if c.before is None or c.after >= c.before or -c.percent < drop_percent:
            continue
        link = c.item.target if c.item.kind == "url" else f"https://www.wildberries.ru/catalog/{c.item.target}/detail.aspx"
        messages.append(
            f"<b>Цена снизилась на {-c.percent:.1f}%</b>\n"
            f"{html.escape(c.item.name)}\n"
            f"{money(c.before)} → <b>{money(c.after)} ₽</b>\n"
            f'<a href="{html.escape(link)}">Открыть товар</a>')
    return messages
