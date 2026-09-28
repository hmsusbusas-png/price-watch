"""config.json и state.json: загрузка, сохранение и правка списка отслеживания."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULTS = {
    "items": [],
    "check_interval_minutes": 30,
    "alert_drop_percent": 5,
    "telegram": {"bot_token": "", "chat_id": ""},
}


class ConfigError(Exception):
    """Битый или неожиданный config.json / state.json."""


def load_config(path: Path) -> dict:
    if not path.exists():
        save_config(path, DEFAULTS)
        print(f"Создан {path} — добавьте позиции через --add-wb / --add-url")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8-sig"))  # utf-8-sig: переживает BOM из Блокнота
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"не удалось прочитать {path}: {e}") from e
    if not isinstance(cfg, dict):
        raise ConfigError(f"{path} должен содержать JSON-объект")
    for key, value in DEFAULTS.items():
        cfg.setdefault(key, copy.deepcopy(value))
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_path(config_path: Path) -> Path:
    return config_path.parent / "state.json"


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"items": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"не удалось прочитать {path}: {e}") from e
    if not isinstance(state, dict) or not isinstance(state.get("items"), dict):
        raise ConfigError(f"{path} повреждён — удалите файл и запустите проверку заново")
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def item_key(item: dict) -> str:
    if item.get("type") == "wb":
        return f"wb:{item.get('sku')}"
    if item.get("type") == "url":
        return f"url:{item.get('url')}"
    raise ConfigError(f"неизвестный тип позиции: {item.get('type')!r}")


def add_item(cfg: dict, item: dict) -> bool:
    key = item_key(item)
    if any(item_key(existing) == key for existing in cfg["items"]):
        return False
    cfg["items"].append(item)
    return True


def remove_item(cfg: dict, target: str) -> bool:
    target = target.strip()
    for item in cfg["items"]:
        if target in (item_key(item), item.get("sku"), item.get("url")):
            cfg["items"].remove(item)
            return True
    return False


def telegram_creds(cfg: dict) -> tuple[str, str] | None:
    """Токен можно держать в config.json или в переменной TG_BOT_TOKEN."""
    telegram = cfg.get("telegram") or {}
    token = os.environ.get("TG_BOT_TOKEN") or telegram.get("bot_token") or ""
    chat_id = str(telegram.get("chat_id") or "")
    if token and chat_id:
        return token, chat_id
    return None
