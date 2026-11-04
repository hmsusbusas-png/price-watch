from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pricewatch.storage import Store

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status: int = 200, body: Any = None, text: str = "") -> None:
        self.status_code = status
        self._body = body
        self.text = text or (json.dumps(body) if body is not None else "")

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Stands in for requests.Session: returns queued responses and remembers the calls."""

    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    get = _next
    post = _next


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def wb_card() -> dict[str, Any]:
    return json.loads((FIXTURES / "wb_card.json").read_text(encoding="utf-8"))
