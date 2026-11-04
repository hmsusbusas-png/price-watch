from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

log = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


class SourceError(Exception):
    """The price could not be fetched: network, blocked request, missing product or unreadable page."""


@dataclass(frozen=True)
class Quote:
    price: float
    title: str | None = None
    old_price: float | None = None


class Source(Protocol):
    kind: str

    def quote(self, target: str, selector: str | None = None) -> Quote: ...


def get(session: requests.Session, url: str, *, params: dict[str, Any] | None = None,
        timeout: float = 10.0, attempts: int = 3, pause: float = 2.0) -> requests.Response:
    """GET with a few retries on network errors and 5xx. 4xx is returned to the caller at once."""
    last: str = "no attempts"
    for attempt in range(1, attempts + 1):
        try:
            resp = session.get(url, params=params, headers=BROWSER_HEADERS, timeout=timeout)
        except requests.Timeout:
            last = f"no answer in {timeout:g} s"
        except requests.RequestException as exc:
            last = exc.__class__.__name__
        else:
            if resp.status_code < 500:
                return resp
            last = f"HTTP {resp.status_code}"
        log.warning("%s: %s, attempt %d of %d", url, last, attempt, attempts)
        if attempt < attempts:
            time.sleep(pause * attempt)
    raise SourceError(f"{url}: {last}")
