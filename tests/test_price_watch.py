"""Тесты: селекторы, разбор цен, логика алертов и прогон проверки с подменой источника.

Запуск: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pwconfig
import sources
import watcher

FIXTURE = (Path(__file__).parent / "fixtures" / "sample.html").resolve().as_uri()


class SelectorTests(unittest.TestCase):
    def test_file_url_price(self):
        self.assertEqual(sources.page_price(FIXTURE, "div#product span.product-price"), 2499.9)

    def test_selector_by_class_only(self):
        self.assertEqual(sources.page_price(FIXTURE, ".old-price"), 3199.0)

    def test_missing_selector(self):
        with self.assertRaises(sources.SourceError):
            sources.page_price(FIXTURE, "span.nothing-here")

    def test_parse_price_formats(self):
        cases = {"2 499,90 ₽": 2499.9, "$1,234.56": 1234.56,
                 "1 999": 1999.0, "12,50": 12.5, "7 €": 7.0}
        for text, expected in cases.items():
            self.assertEqual(sources.parse_price(text), expected, text)


class AlertTests(unittest.TestCase):
    def test_drop_over_threshold(self):
        msg = watcher.build_message({"name": "Keyboard"}, 100.0, 90.0, 5)
        self.assertIn("Цена упала!", msg)
        self.assertIn("-10.0%", msg)

    def test_small_change_is_not_alert(self):
        msg = watcher.build_message({"name": "Keyboard"}, 100.0, 98.0, 5)
        self.assertNotIn("Цена упала!", msg)
        self.assertIn("Изменение цены", msg)


class CheckTests(unittest.TestCase):
    """Полный цикл проверки с подменой источника — без сети."""

    def test_check_records_state_and_alerts_on_drop(self):
        cfg = {"items": [{"type": "wb", "sku": "1", "name": "Mock item"}],
               "alert_drop_percent": 5}
        prices = iter([100.0, 100.0, 92.0])

        def fake_fetch(item, timeout=10.0, retries=3):
            return next(prices)

        original = sources.fetch_price
        sources.fetch_price = fake_fetch
        try:
            state = {"items": {}}
            self.assertEqual(watcher.check_once(cfg, state), [])  # базовая цена
            self.assertEqual(watcher.check_once(cfg, state), [])  # без изменений
            notices = watcher.check_once(cfg, state)              # падение на 8%
        finally:
            sources.fetch_price = original
        self.assertEqual(state["items"]["wb:1"]["price"], 92.0)
        self.assertEqual(len(notices), 1)
        self.assertIn("Цена упала!", notices[0])

    def test_config_roundtrip(self):
        cfg_path = Path(tempfile.mkdtemp()) / "config.json"
        cfg = pwconfig.load_config(cfg_path)  # автосоздание с дефолтами
        self.assertEqual(cfg["check_interval_minutes"], 30)
        self.assertTrue(pwconfig.add_item(cfg, {"type": "wb", "sku": "42", "name": "X"}))
        self.assertFalse(pwconfig.add_item(cfg, {"type": "wb", "sku": "42", "name": "dup"}))
        pwconfig.save_config(cfg_path, cfg)
        self.assertEqual(pwconfig.load_config(cfg_path)["items"][0]["sku"], "42")
        self.assertTrue(pwconfig.remove_item(cfg, "42"))
        self.assertFalse(pwconfig.remove_item(cfg, "42"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
