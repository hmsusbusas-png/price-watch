"""Уведомления в Telegram через Bot API."""
from __future__ import annotations

import requests

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramError(Exception):
    """Telegram не принял сообщение: сеть, токен или chat_id."""


def send(token: str, chat_id: str, text: str, timeout: float = 10.0) -> None:
    try:
        resp = requests.post(
            API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=timeout)
    except requests.RequestException as e:
        raise TelegramError(f"нет связи с Telegram ({e.__class__.__name__})") from e
    if resp.status_code != 200:
        detail = resp.json().get("description", resp.text[:120]) if resp.text else ""
        raise TelegramError(f"Telegram отклонил сообщение: HTTP {resp.status_code} {detail}")
