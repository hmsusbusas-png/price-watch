from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

TOKEN = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,}$")
CHAT = re.compile(r"^(-?\d+|@[A-Za-z][A-Za-z0-9_]{4,})$")


class SettingsError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    db_path: Path
    interval_minutes: int
    drop_percent: float
    telegram_token: str | None
    telegram_chat: str | None

    @property
    def telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat)


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=value lines; # comments and surrounding quotes are allowed. Real environment variables win."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise SettingsError(f"{path}, строка {number}: нужен формат КЛЮЧ=значение")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load(env_file: Path | str = ".env", environ: dict[str, str] | None = None) -> Settings:
    env = {**read_env_file(Path(env_file)), **(os.environ if environ is None else environ)}

    def number(key: str, default: str, kind: type[int] | type[float], minimum: float) -> float:
        raw = env.get(key) or default
        try:
            value = kind(raw)
        except ValueError:
            raise SettingsError(f"{key} должно быть числом, сейчас {raw!r}") from None
        if value < minimum:
            raise SettingsError(f"{key} должно быть не меньше {minimum:g}, сейчас {raw!r}")
        return value

    token = env.get("TELEGRAM_BOT_TOKEN") or None
    chat = env.get("TELEGRAM_CHAT_ID") or None
    if token and not TOKEN.match(token):
        raise SettingsError(
            "TELEGRAM_BOT_TOKEN не похож на токен бота: ожидается вид 123456789:AA..., его выдаёт @BotFather")
    if chat and not CHAT.match(chat):
        raise SettingsError("Укажите в TELEGRAM_CHAT_ID число (id чата) или @имя канала")
    if bool(token) != bool(chat):
        raise SettingsError("для уведомлений нужны оба значения: TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")

    return Settings(
        db_path=Path(env.get("PRICEWATCH_DB") or "data/pricewatch.db"),
        interval_minutes=int(number("CHECK_INTERVAL_MINUTES", "60", int, 1)),
        drop_percent=float(number("ALERT_DROP_PERCENT", "5", float, 0)),
        telegram_token=token,
        telegram_chat=chat,
    )
