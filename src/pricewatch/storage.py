from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id        INTEGER PRIMARY KEY,
    kind      TEXT NOT NULL,
    target    TEXT NOT NULL,
    selector  TEXT,
    name      TEXT NOT NULL,
    added_at  TEXT NOT NULL,
    UNIQUE (kind, target)
);
CREATE TABLE IF NOT EXISTS prices (
    item_id    INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    checked_at TEXT NOT NULL,
    price      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS prices_by_item ON prices (item_id, checked_at);
"""


@dataclass(frozen=True)
class Item:
    id: int
    kind: str
    target: str
    selector: str | None
    name: str


@dataclass(frozen=True)
class Point:
    at: datetime
    price: float


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def add(self, kind: str, target: str, name: str, selector: str | None = None) -> Item | None:
        """Returns None when the item is already tracked."""
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO items (kind, target, selector, name, added_at) VALUES (?, ?, ?, ?, ?)",
                    (kind, target, selector, name, now()))
        except sqlite3.IntegrityError:
            return None
        return Item(int(cur.lastrowid or 0), kind, target, selector, name)

    def remove(self, item_id: int) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM items WHERE id = ?", (item_id,)).rowcount > 0

    def rename(self, item_id: int, name: str) -> None:
        with self.db:
            self.db.execute("UPDATE items SET name = ? WHERE id = ?", (name, item_id))

    def items(self) -> list[Item]:
        rows = self.db.execute("SELECT id, kind, target, selector, name FROM items ORDER BY id")
        return [Item(**dict(r)) for r in rows]

    def get(self, item_id: int) -> Item | None:
        row = self.db.execute("SELECT id, kind, target, selector, name FROM items WHERE id = ?", (item_id,)).fetchone()
        return Item(**dict(row)) if row else None

    def record(self, item_id: int, price: float, at: str | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO prices (item_id, checked_at, price) VALUES (?, ?, ?)",
                            (item_id, at or now(), price))

    def last_price(self, item_id: int) -> float | None:
        row = self.db.execute(
            "SELECT price FROM prices WHERE item_id = ? ORDER BY checked_at DESC, rowid DESC LIMIT 1",
            (item_id,)).fetchone()
        return float(row["price"]) if row else None

    def history(self, item_id: int) -> list[Point]:
        rows = self.db.execute("SELECT checked_at, price FROM prices WHERE item_id = ? ORDER BY checked_at, rowid",
                               (item_id,))
        return [Point(datetime.fromisoformat(r["checked_at"]), float(r["price"])) for r in rows]
