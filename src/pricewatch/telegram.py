from __future__ import annotations

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramError(Exception):
    pass


def send(token: str, chat: str, text: str, session: requests.Session | None = None, timeout: float = 10.0) -> None:
    http = session or requests.Session()
    try:
        resp = http.post(API.format(token=token), timeout=timeout, json={
            "chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    except requests.RequestException as exc:
        raise TelegramError(f"нет связи с Telegram ({exc.__class__.__name__})") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code == 200 and body.get("ok"):
        return
    detail = body.get("description") or resp.text[:120]
    if resp.status_code == 401:
        detail = "токен не принят, проверьте TELEGRAM_BOT_TOKEN"
    elif resp.status_code == 400 and "chat not found" in str(detail):
        detail = "чат не найден: напишите боту /start или добавьте его в канал"
    raise TelegramError(f"Telegram отклонил сообщение: {detail}")
