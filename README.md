# price-watch

Мониторинг цен с уведомлениями в Telegram: следит за товарами на Wildberries (по артикулу) и на любых сайтах (по URL + CSS-селектору), присылает сообщение, когда цена упала ниже порога или просто изменилась. Чистый Python + requests — без браузера и Selenium.

```
🔻 Цена упала!
Mechanical Keyboard K87
3 199,00 → 2 499,90 ₽ (-21.9%)
```

## Возможности

- два типа источников: карточка Wildberries по артикулу (`type: "wb"`) и любая HTML-страница через встроенный селектор-движок (`type: "url"`; поддерживаются `tag`, `#id`, `.class`, `[attr=value]` и цепочки вложенности — BeautifulSoup не нужен)
- уведомление в Telegram при любом изменении цены; падение на `alert_drop_percent` и сильнее помечается как «Цена упала!»
- последние цены хранятся в `state.json`, перезапуски безопасны
- CLI: разовая проверка, режим демона, dry-run, добавление и удаление позиций прямо из командной строки
- вежливый по умолчанию: повторы с паузой при сетевых ошибках, задержка между запросами, логи в `logs/watch.log` и консоль
- одна сломанная позиция (битый конфиг, умерший селектор, нет сети) пишется в лог и пропускается — проверка целиком не падает
- осмысленные коды выхода: `0` — успех, `1` — ошибка конфига, `2` — ошибка запуска; удобно вешать на cron

## Быстрый старт

1. Склонируйте репозиторий и установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

2. Создайте бота у [@BotFather](https://t.me/BotFather) (`/newbot`) и скопируйте токен. Напишите своему боту любое сообщение и получите `chat_id` через `https://api.telegram.org/bot<ТОКЕН>/getUpdates` (поле `"chat":{"id": ...}`).
3. Заполните `config.json`:

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

   Токен можно не класть в конфиг, а держать в переменной окружения `TG_BOT_TOKEN`.

4. Проверьте, что всё читается: `python watcher.py --once --dry-run` — без отправки в Telegram, только печать.

## Команды

```bash
python watcher.py --once                  # одна проверка всех позиций
python watcher.py --daemon                # цикл каждые check_interval_minutes
python watcher.py --daemon --dry-run      # цикл без отправки в Telegram
python watcher.py --status                # сохранённые цены из state.json

python watcher.py --add-wb 155713071 --name "Мышка беспроводная"
python watcher.py --add-url https://shop.example.com/p/42 --selector "span.price" --name "Товар"
python watcher.py --remove 155713071      # по артикулу или по URL
```

Сетевые ошибки повторяются (3 попытки с паузой) и логируются. Коды выхода: `0` — успех, `1` — ошибка конфига (нечитаемый `config.json`/`state.json`, нечисловой `check_interval_minutes`, нет цели для `--remove`), `2` — ошибка запуска (не выбран режим, `--add-wb` вместе с `--add-url`, смешивание `--add-*`/`--remove` с `--once`/`--daemon`/`--status`).

## По расписанию

Windows (планировщик задач):

```bat
schtasks /Create /TN "PriceWatch" /TR "python C:\path\to\price-watch\watcher.py --once" /SC MINUTE /MO 30
```

Linux / macOS (cron):

```cron
*/30 * * * * cd /path/to/price-watch && /usr/bin/python3 watcher.py --once >> logs/cron.out 2>&1
```

`--daemon` держит процесс запущенным сам; вариант с `--once` по расписанию надёжнее — упавший запуск просто перезапустит планировщик.

## Честно об ограничениях

- WB с некоторых IP отдаёт 403: если карточки не тянутся, попробуйте позже или с другого адреса.
- url-источник — простой селектор-движок (`tag`, `#id`, `.class`, `[attr=value]`, вложенность): страницы, где цена рисуется JavaScript'ом или спрятана в теневом DOM, он не разберёт.
- проблемы доставки в Telegram логируются и не роняют проверку.

## Структура

```
price-watch/
├── watcher.py    # CLI, цикл проверок, логика уведомлений
├── sources.py    # API Wildberries + источник HTML-страниц (селектор-движок)
├── telegram.py   # клиент Telegram Bot API
├── pwconfig.py   # работа с config.json / state.json
├── config.json   # отслеживаемые позиции и настройки (редактируйте его)
├── state.json    # последние цены (создаётся сам, не коммитьте)
├── tests/        # юнит-тесты с моком источника цен
└── requirements.txt
```

## Тесты

```bash
python -m unittest discover -s tests -v
python watcher.py --config config.json --once --dry-run
```

## Стек

Python + requests; тесты — unittest.

---

## EN

Price monitoring with Telegram alerts: watch products on Wildberries (by SKU) and on any website (URL + CSS selector); get a message when a price drops past your threshold or changes. Pure Python + requests — no browser, no Selenium. One-shot check, daemon mode, dry-run, add/remove from the CLI; details in the Russian section above.
