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
    # ответ может быть не-JSON (прокси, HTML-заглушка) — не падаем на .json()
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        if payload.get("ok"):
            return  # HTTP 200 + ok:true — сообщение принято
        detail = str(payload.get("description") or payload)[:200]
    else:
        detail = (resp.text or "").strip()[:120] or "ответ не в JSON"
    raise TelegramError(f"Telegram отклонил сообщение: HTTP {resp.status_code} {detail}")
