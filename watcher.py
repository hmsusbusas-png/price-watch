"""price-watch — мониторинг цен товаров с уведомлениями в Telegram."""
from __future__ import annotations

import argparse
import html
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pwconfig
import sources
import telegram as tg

log = logging.getLogger("price-watch")

REQUEST_PAUSE = 1.5  # пауза между запросами, чтобы не дёргать сайты подряд


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def fmt_price(price: float) -> str:
    return f"{price:,.2f}".replace(",", " ")


def print_status(cfg: dict, state: dict) -> None:
    creds = pwconfig.telegram_creds(cfg)
    entries = state.get("items") or {}
    items = cfg.get("items") or []
    print(f"Позиций в конфиге: {len(items)}; записей в state: {len(entries)}")
    print(f"Интервал проверки: {cfg.get('check_interval_minutes')} мин; "
          f"порог падения: {cfg.get('alert_drop_percent')}%")
    print(f"Telegram: {'настроен' if creds else 'НЕ настроен (TG_BOT_TOKEN или config.json)'}")
    if not items:
        print("Список пуст — добавьте позиции: --add-wb SKU --name \"...\" "
              "или --add-url URL --selector \"...\" --name \"...\"")
        return
    print()
    for item in items:
        key = pwconfig.item_key(item)
        entry = entries.get(key) or {}
        name = (item.get("name") or key)[:38]
        price = f"{fmt_price(entry['price'])} ₽" if "price" in entry else "—"
        checked = entry.get("ts") or "ещё не проверялся"
        print(f"  {name:<38} {price:>14}  {checked}")


def build_message(item: dict, prev: float, current: float, drop_threshold: float) -> str:
    """Сообщение о смене цены; падение сильнее порога помечается как алерт."""
    diff = current - prev
    pct = diff / prev * 100 if prev else 0.0
    name = html.escape(item.get("name") or pwconfig.item_key(item))
    if diff < 0 and abs(pct) >= drop_threshold:
        title, mark = "Цена упала!", "🔻"
    else:
        title, mark = "Изменение цены", "🔺" if diff > 0 else "ℹ️"
    return (f"{mark} <b>{title}</b>\n"
            f"{name}\n"
            f"{fmt_price(prev)} → {fmt_price(current)} ₽ ({pct:+.1f}%)")


def deliver(notices: list[str], creds: tuple[str, str] | None, dry_run: bool) -> None:
    if not notices:
        return
    if dry_run:
        for text in notices:
            print("--- dry-run: сообщение не отправлено ---")
            print(text)
        return
    if creds is None:
        log.warning("Telegram не настроен (bot_token/chat_id в config.json или переменная "
                    "TG_BOT_TOKEN) — уведомления только в лог:")
        for text in notices:
            print(text)
        return
    token, chat_id = creds
    for text in notices:
        try:
            tg.send(token, chat_id, text)
            log.info("уведомление отправлено в Telegram")
        except tg.TelegramError as exc:
            log.error("%s", exc)


def check_once(cfg: dict, state: dict, *, timeout: float = 10.0) -> list[str]:
    """Опросить все позиции, обновить state и вернуть тексты уведомлений."""
    items = cfg.get("items") or []
    if not items:
        log.warning("Список отслеживания пуст — добавьте позиции через --add-wb / --add-url")
        return []
    entries = state.setdefault("items", {})
    notices: list[str] = []
    for index, item in enumerate(items):
        key = pwconfig.item_key(item)
        name = item.get("name") or key
        try:
            price = sources.fetch_price(item, timeout=timeout)
        except sources.SourceError as exc:
            log.error("%s: %s", name, exc)
            continue
        prev = (entries.get(key) or {}).get("price")
        entries[key] = {"price": price, "ts": datetime.now().isoformat(timespec="seconds"),
                        "name": name}
        if prev is None:
            log.info("%s: базовая цена %s ₽ записана", name, fmt_price(price))
        elif price == prev:
            log.info("%s: без изменений (%s ₽)", name, fmt_price(price))
        else:
            log.info("%s: цена изменилась: %s → %s ₽", name, fmt_price(prev), fmt_price(price))
            notices.append(build_message(item, prev, price,
                                         float(cfg.get("alert_drop_percent") or 0)))
        if index < len(items) - 1:
            time.sleep(REQUEST_PAUSE)
    return notices


def cmd_add(cfg: dict, cfg_path: Path, args: argparse.Namespace) -> None:
    if args.add_wb:
        item = {"type": "wb", "sku": args.add_wb.strip(), "name": (args.name or "").strip()}
    else:
        if not args.selector:
            sys.exit("Ошибка: для --add-url нужен --selector — CSS-селектор блока с ценой")
        item = {"type": "url", "url": args.add_url.strip(),
                "selector": args.selector.strip(), "name": (args.name or "").strip()}
    if pwconfig.add_item(cfg, item):
        pwconfig.save_config(cfg_path, cfg)
        print(f"Добавлено: {pwconfig.item_key(item)}")
    else:
        print("Эта позиция уже отслеживается")


def cmd_remove(cfg: dict, cfg_path: Path, target: str) -> None:
    if pwconfig.remove_item(cfg, target):
        pwconfig.save_config(cfg_path, cfg)
        print(f"Удалено: {target}")
    else:
        sys.exit(f"Не найдено в списке: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="price-watch",
        description="Мониторинг цен (Wildberries и любые страницы) с уведомлениями в Telegram")
    parser.add_argument("--config", default="config.json", help="путь к config.json")
    parser.add_argument("--once", action="store_true", help="одна проверка и выход")
    parser.add_argument("--dry-run", action="store_true",
                        help="не отправлять в Telegram, только печатать")
    parser.add_argument("--status", action="store_true", help="показать сохранённые цены")
    parser.add_argument("--add-wb", metavar="SKU", help="добавить товар Wildberries по артикулу")
    parser.add_argument("--add-url", metavar="URL", help="добавить произвольную страницу")
    parser.add_argument("--selector", help="CSS-селектор блока с ценой (для --add-url)")
    parser.add_argument("--name", help="понятное название позиции")
    parser.add_argument("--remove", metavar="SKU_OR_URL", help="убрать позицию из списка")
    args = parser.parse_args()

    if not any([args.once, args.status, args.add_wb, args.add_url, args.remove]):
        parser.print_help()
        sys.exit(2)

    cfg_path = Path(args.config)
    try:
        cfg = pwconfig.load_config(cfg_path)
    except pwconfig.ConfigError as e:
        sys.exit(f"Ошибка конфига: {e}")

    if args.once:
        setup_logging()
        state_path = pwconfig.state_path(cfg_path)
        state = pwconfig.load_state(state_path)
        notices = check_once(cfg, state)
        pwconfig.save_state(state_path, state)
        deliver(notices, pwconfig.telegram_creds(cfg), args.dry_run)
    elif args.add_wb or args.add_url:
        cmd_add(cfg, cfg_path, args)
    elif args.remove:
        cmd_remove(cfg, cfg_path, args.remove)
    elif args.status:
        print_status(cfg, pwconfig.load_state(pwconfig.state_path(cfg_path)))


if __name__ == "__main__":
    main()
