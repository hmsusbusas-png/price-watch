from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import report, settings, telegram
from .checker import alerts, check, money
from .sources import SourceError, Wildberries, make
from .storage import Store

log = logging.getLogger("pricewatch")


def cmd_add(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    if args.kind == "url" and not args.selector:
        print("Для страницы нужен --selector, например --selector \"span.price\"", file=sys.stderr)
        return 2
    target = args.target.strip()
    try:
        quote = make(args.kind).quote(target, args.selector)
    except SourceError as exc:
        print(f"Не удалось получить цену: {exc}", file=sys.stderr)
        return 1
    name = args.name or quote.title or target
    item = store.add(args.kind, target, name[:120], args.selector)
    if item is None:
        print("Этот товар уже отслеживается")
        return 0
    store.record(item.id, quote.price)
    print(f"Добавлен №{item.id}: {item.name}, сейчас {money(quote.price)} ₽")
    return 0


def cmd_list(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    items = store.items()
    if not items:
        print("Список пуст. Добавьте товар: pricewatch add wb 123456 или pricewatch add url URL --selector ...")
        return 0
    for item in items:
        last = store.last_price(item.id)
        price = f"{money(last)} ₽" if last is not None else "нет данных"
        print(f"{item.id:>3}  {item.kind:<3}  {item.name[:48]:<48}  {price:>12}")
    return 0


def cmd_remove(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    if store.remove(args.id):
        print(f"Удалён №{args.id}")
        return 0
    print(f"Нет товара №{args.id}", file=sys.stderr)
    return 1


def run_check(store: Store, cfg: settings.Settings, dry_run: bool) -> int:
    if not store.items():
        print("Список пуст, проверять нечего. Добавьте товар: pricewatch add wb 123456")
        return 0
    result = check(store)
    for change in result.changes:
        before = "нет данных" if change.before is None else f"{money(change.before)} ₽"
        print(f"{change.item.name[:48]:<48}  {before:>12} → {money(change.after)} ₽")
    for item, error in result.failed:
        print(f"{item.name[:48]:<48}  ошибка: {error}", file=sys.stderr)
    messages = alerts(result.changes, cfg.drop_percent)
    if messages and not dry_run and cfg.telegram_token and cfg.telegram_chat:
        for text in messages:
            try:
                telegram.send(cfg.telegram_token, cfg.telegram_chat, text)
            except telegram.TelegramError as exc:
                log.error("%s", exc)
    elif messages:
        reason = "--dry-run" if dry_run else "Telegram не настроен"
        print(f"\n{len(messages)} уведомл. не отправлено ({reason}):")
        for text in messages:
            print(text)
    return 1 if result.failed and not result.changes else 0


def cmd_check(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    return run_check(store, cfg, args.dry_run)


def cmd_watch(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    if not store.items():
        print("Не за чем следить. Сначала добавьте товар: pricewatch add wb 123456", file=sys.stderr)
        return 2
    log.info("проверка каждые %d мин, уведомления %s", cfg.interval_minutes,
             "в Telegram" if cfg.telegram else "выключены")
    while True:
        run_check(store, cfg, dry_run=False)
        time.sleep(cfg.interval_minutes * 60)


def cmd_history(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    item = store.get(args.id)
    if item is None:
        print(f"Нет товара №{args.id}", file=sys.stderr)
        return 1
    print(item.name)
    for point in store.history(item.id)[-args.last:]:
        print(f"  {point.at:%d.%m.%Y %H:%M}  {money(point.price):>12} ₽")
    return 0


def cmd_chart(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    item = store.get(args.id)
    if item is None:
        print(f"Нет товара №{args.id}", file=sys.stderr)
        return 1
    try:
        path = report.chart_png(item, store.history(item.id), Path(args.out or f"chart-{item.id}.png"))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"График: {path.resolve()}")
    return 0


def cmd_export(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    path = report.history_workbook(store, Path(args.out))
    print(f"Excel: {path.resolve()}")
    return 0


def cmd_search(store: Store, cfg: settings.Settings, args: argparse.Namespace) -> int:
    try:
        products = Wildberries().search(args.query, pages=args.pages)
    except SourceError as exc:
        print(f"Поиск не удался: {exc}", file=sys.stderr)
        return 1
    for p in products[:30]:
        print(f"{p.sku:>11}  {p.title[:50]:<50}  {money(p.price):>10} ₽  ★{p.rating:.1f}")
    print(f"\nНайдено: {len(products)}")
    if args.excel:
        print(f"Excel: {report.search_workbook(products, Path(args.excel)).resolve()}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pricewatch", description="Цены на Wildberries и любых сайтах: история, графики, Excel, Telegram")
    p.add_argument("--env", default=".env", help="файл с настройками (по умолчанию .env)")
    p.add_argument("-v", "--verbose", action="store_true", help="подробный лог")
    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="начать следить за товаром")
    add.add_argument("kind", choices=["wb", "url"], help="wb: артикул Wildberries; url: страница магазина")
    add.add_argument("target", help="артикул или адрес страницы")
    add.add_argument("--selector", help="CSS-селектор блока с ценой, для url")
    add.add_argument("--name", help="своё название вместо заголовка страницы")
    add.set_defaults(run=cmd_add)

    sub.add_parser("list", help="что отслеживается").set_defaults(run=cmd_list)

    rm = sub.add_parser("remove", help="перестать следить")
    rm.add_argument("id", type=int)
    rm.set_defaults(run=cmd_remove)

    chk = sub.add_parser("check", help="проверить цены один раз")
    chk.add_argument("--dry-run", action="store_true", help="не отправлять в Telegram, показать сообщения")
    chk.set_defaults(run=cmd_check)

    sub.add_parser("watch", help="проверять по кругу с интервалом CHECK_INTERVAL_MINUTES").set_defaults(run=cmd_watch)

    hist = sub.add_parser("history", help="история цены")
    hist.add_argument("id", type=int)
    hist.add_argument("--last", type=int, default=20, help="сколько последних замеров показать")
    hist.set_defaults(run=cmd_history)

    ch = sub.add_parser("chart", help="график цены в PNG")
    ch.add_argument("id", type=int)
    ch.add_argument("--out", help="имя файла, по умолчанию chart-<id>.png")
    ch.set_defaults(run=cmd_chart)

    ex = sub.add_parser("export", help="вся история в Excel с графиками")
    ex.add_argument("--out", default="prices.xlsx")
    ex.set_defaults(run=cmd_export)

    se = sub.add_parser("search", help="поиск на Wildberries")
    se.add_argument("query")
    se.add_argument("--pages", type=int, default=1, help="страниц выдачи, по 100 товаров")
    se.add_argument("--excel", metavar="FILE.xlsx")
    se.set_defaults(run=cmd_search)
    return p


def utf8_console() -> None:
    # Windows pipes and redirects default to the ANSI code page, which cannot print Cyrillic.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    try:
        cfg = settings.load(args.env)
    except settings.SettingsError as exc:
        print(f"Ошибка в настройках: {exc}", file=sys.stderr)
        return 2
    store = Store(cfg.db_path)
    try:
        return int(args.run(store, cfg, args))
    except KeyboardInterrupt:
        return 130
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
