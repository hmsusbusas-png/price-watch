from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from pricewatch import report, settings, telegram
from pricewatch.checker import Change, alerts, check, money
from pricewatch.sources import Quote, SourceError

from .conftest import FakeResponse, FakeSession


class ScriptedSource:
    kind = "wb"

    def __init__(self, prices: dict[str, float | Exception]) -> None:
        self.prices = prices

    def quote(self, target, selector=None):
        value = self.prices[target]
        if isinstance(value, Exception):
            raise value
        return Quote(price=value)


def test_first_check_records_price_without_alert(store):
    item = store.add("wb", "1", "Чайник")
    result = check(store, source_for=lambda kind: ScriptedSource({"1": 1990.0}))
    assert store.last_price(item.id) == 1990.0
    assert alerts(result.changes, drop_percent=5) == []


def test_drop_over_threshold_alerts(store):
    item = store.add("wb", "1", "Чайник <стеклянный>")
    store.record(item.id, 2000.0)
    result = check(store, source_for=lambda kind: ScriptedSource({"1": 1800.0}))
    [message] = alerts(result.changes, drop_percent=5)
    assert "10.0%" in message and "1 800" in message
    assert "&lt;стеклянный&gt;" in message
    assert "wildberries.ru/catalog/1/" in message


def test_small_drop_and_rise_do_not_alert(store):
    a = store.add("wb", "1", "a")
    b = store.add("wb", "2", "b")
    store.record(a.id, 1000.0)
    store.record(b.id, 1000.0)
    result = check(store, source_for=lambda kind: ScriptedSource({"1": 980.0, "2": 1200.0}))
    assert len(result.changes) == 2
    assert alerts(result.changes, drop_percent=5) == []


def test_same_price_is_not_stored_twice(store):
    item = store.add("wb", "1", "a")
    store.record(item.id, 500.0)
    check(store, source_for=lambda kind: ScriptedSource({"1": 500.0}))
    assert len(store.history(item.id)) == 1


def test_one_broken_item_does_not_stop_the_rest(store):
    store.add("wb", "1", "a")
    store.add("wb", "2", "b")
    result = check(store, source_for=lambda kind: ScriptedSource({"1": SourceError("403"), "2": 10.0}))
    assert [i.name for i, _ in result.failed] == ["a"]
    assert [c.item.name for c in result.changes] == ["b"]


def test_duplicate_item_is_refused(store):
    assert store.add("wb", "1", "a") is not None
    assert store.add("wb", "1", "a again") is None


def test_change_percent():
    assert Change(item=None, before=200.0, after=150.0).percent == -25.0  # type: ignore[arg-type]


def test_money_format():
    assert money(1234.5) == "1 234,50"
    assert money(990.0) == "990"


def test_settings_defaults(tmp_path):
    cfg = settings.load(tmp_path / "missing.env", environ={})
    assert cfg.interval_minutes == 60 and cfg.drop_percent == 5 and not cfg.telegram


def test_settings_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comment\nTELEGRAM_BOT_TOKEN="123456789:test-token-for-unit-tests-only-xxxx"\n'
                   "TELEGRAM_CHAT_ID=-100123\nCHECK_INTERVAL_MINUTES=15\n", encoding="utf-8")
    cfg = settings.load(env, environ={})
    assert cfg.telegram and cfg.interval_minutes == 15 and cfg.telegram_chat == "-100123"


@pytest.mark.parametrize(("env", "message"), [
    ({"TELEGRAM_BOT_TOKEN": "12345"}, "не похож на токен"),
    ({"TELEGRAM_BOT_TOKEN": "123456789:test-token-for-unit-tests-only-xxxx"}, "оба значения"),
    ({"CHECK_INTERVAL_MINUTES": "0"}, "не меньше 1"),
    ({"ALERT_DROP_PERCENT": "пять"}, "числом"),
])
def test_settings_errors(tmp_path, env, message):
    with pytest.raises(settings.SettingsError, match=message):
        settings.load(tmp_path / "missing.env", environ=env)


def test_export_workbook(store, tmp_path):
    item = store.add("url", "https://example.com/p", "Клавиатура", "span.price")
    for day, price in [("2026-10-01T09:00:00", 3000.0), ("2026-10-08T09:00:00", 2700.0)]:
        store.record(item.id, price, day)
    path = report.history_workbook(store, tmp_path / "out.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames == ["Сводка", "1 Клавиатура"]
    row = [c.value for c in wb["Сводка"][2]]
    assert row[:7] == [1, "Клавиатура", "url", 2700.0, 2700.0, 3000.0, 2]
    assert wb["1 Клавиатура"]._charts


def test_chart_png(store, tmp_path):
    item = store.add("wb", "1", "a")
    store.record(item.id, 10.0, "2026-10-01T09:00:00")
    store.record(item.id, 8.0, "2026-10-02T09:00:00")
    path = report.chart_png(item, store.history(item.id), tmp_path / "c.png")
    assert Path(path).stat().st_size > 1000


def test_chart_needs_two_points(store, tmp_path):
    item = store.add("wb", "1", "a")
    store.record(item.id, 10.0)
    with pytest.raises(ValueError):
        report.chart_png(item, store.history(item.id), tmp_path / "c.png")


def test_telegram_send_ok():
    session = FakeSession(FakeResponse(body={"ok": True}))
    telegram.send("1:x", "42", "<b>hi</b>", session=session)
    url, kwargs = session.calls[0]
    assert url.endswith("/bot1:x/sendMessage") and kwargs["json"]["chat_id"] == "42"


def test_telegram_bad_token_is_explained():
    with pytest.raises(telegram.TelegramError, match="токен не принят"):
        telegram.send("1:x", "42", "hi", session=FakeSession(FakeResponse(401, body={"ok": False})))
