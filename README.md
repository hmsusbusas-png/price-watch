# price-watch

Price monitoring with Telegram alerts. Watch products on **Wildberries** (by SKU)
and on **any website** (by URL + CSS selector); get a Telegram message when a price
drops past your threshold or simply changes. Pure Python + `requests`, no browser,
no Selenium.

```
🔻 Price drop!
Mechanical Keyboard K87
3 199,00 → 2 499,90 ₽ (-21.9%)
```

## Features

- **Two source types** — Wildberries card API by SKU (`type: "wb"`) and any HTML page
  parsed with a small built-in selector engine (`type: "url"`; supports `tag`, `#id`,
  `.class`, `[attr=value]` and descendant chains — no BeautifulSoup needed).
- **Alerts** — a Telegram message on any price change; drops bigger than
  `alert_drop_percent` are flagged as *Price drop!*.
- **State** — last seen prices live in `state.json`, so restarts are safe.
- **CLI** — one-shot check, daemon mode, dry-run, add/remove items right from the
  command line.
- **Polite by default** — retries with backoff on network errors, pause between
  requests, everything logged to `logs/watch.log` and the console.

## Setup

```bash
pip install -r requirements.txt
```

**1. Create a Telegram bot** — message [@BotFather](https://t.me/BotFather),
send `/newbot`, copy the token. Then send any message to your new bot and get your
chat id via `https://api.telegram.org/bot<TOKEN>/getUpdates` (`"chat":{"id": ...}`).

**2. Fill `config.json`:**

```json
{
  "items": [
    { "type": "wb",  "sku": "155713071", "name": "Wildberries item" },
    { "type": "url", "url": "https://shop.example.com/product/42",
      "selector": "span.product-price", "name": "Shop item" }
  ],
  "check_interval_minutes": 30,
  "alert_drop_percent": 5,
  "telegram": { "bot_token": "123456:ABC...", "chat_id": "11111111" }
}
```

The bot token can also be kept out of the config in the `TG_BOT_TOKEN`
environment variable.

## Usage

```bash
python watcher.py --once                  # single check of all items
python watcher.py --daemon                # check in a loop every N minutes
python watcher.py --daemon --dry-run      # loop without sending to Telegram
python watcher.py --status                # show saved prices from state.json

python watcher.py --add-wb 155713071 --name "Wireless mouse"
python watcher.py --add-url https://shop.example.com/p/42 --selector "span.price" --name "Shop item"
python watcher.py --remove 155713071      # by SKU or by URL
```

Exit codes: `0` — ok, `2` — CLI usage error. Network errors are retried (3 attempts
with backoff) and logged; one broken item never stops the whole check.

## Run on a schedule

**Windows (Task Scheduler):**

```bat
schtasks /Create /TN "PriceWatch" /TR "python C:\path\to\price-watch\watcher.py --once" /SC MINUTE /MO 30
```

**Linux / macOS (cron):**

```cron
*/30 * * * * cd /path/to/price-watch && /usr/bin/python3 watcher.py --once >> logs/cron.out 2>&1
```

(`--daemon` keeps the process running by itself; the scheduled `--once` variant is
more robust — a crashed run is simply restarted by the scheduler.)

## Project layout

```
watcher.py    CLI, check loop, alert logic
sources.py    Wildberries API + HTML page source (selector engine)
telegram.py   Telegram Bot API client
pwconfig.py   config.json / state.json handling
config.json   tracked items and settings (edit this)
state.json    last seen prices (created automatically, do not commit)
tests/        unit tests with a mocked price source
```

## Testing

```bash
python -m unittest discover -s tests -v
python watcher.py --config config.json --once --dry-run
```

---

## price-watch на русском

Мониторинг цен с уведомлениями в Telegram: Wildberries по артикулу и любые сайты
по URL + CSS-селектору. Сообщение приходит при любом изменении цены, а падение
больше `alert_drop_percent` помечается как «Цена упала!».

**Установка и настройка**

1. `pip install -r requirements.txt`
2. Создайте бота у [@BotFather](https://t.me/BotFather) (`/newbot`), скопируйте токен.
3. Узнайте свой `chat_id`: напишите боту любое сообщение, затем откройте
   `https://api.telegram.org/bot<ТОКЕН>/getUpdates`.
4. Заполните `config.json` (токен можно держать в переменной окружения `TG_BOT_TOKEN`).

**Команды**

```bash
python watcher.py --once              # одна проверка
python watcher.py --daemon            # цикл с интервалом check_interval_minutes
python watcher.py --once --dry-run    # без отправки в Telegram, только печать
python watcher.py --status            # сохранённые цены из state.json
python watcher.py --add-wb 155713071 --name "Мышка беспроводная"
python watcher.py --add-url https://shop.example.com/p/42 --selector "span.price" --name "Товар"
python watcher.py --remove 155713071  # по артикулу или URL
```

**Автозапуск**

Windows: `schtasks /Create /TN "PriceWatch" /TR "python C:\путь\к\price-watch\watcher.py --once" /SC MINUTE /MO 30`

cron: `*/30 * * * * cd /путь/к/price-watch && python3 watcher.py --once >> logs/cron.out 2>&1`

Логи пишутся в `logs/watch.log` и в консоль; сетевые ошибки повторяются с паузой,
один упавший товар не ломает всю проверку. Тесты: `python -m unittest discover -s tests -v`.
