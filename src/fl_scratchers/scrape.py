"""Network layer — JSON API calls to floridalottery.com.

No HTML scraping; both endpoints return clean JSON. See PRD §5.
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests

LIST_URL = (
    "https://floridalottery.com/content/flalottery-web/us/en/"
    "games/scratch-offs/view.scratch-offs.json"
)
DETAIL_URL = (
    "https://apim-website-prod-eastus.azure-api.net/scratchgamesapp/getscratchinfo"
)
TOP_REMAINING_URL = (
    "https://apim-website-prod-eastus.azure-api.net/scratchgamesapp/getTopPrizesRemaining"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
DETAIL_HEADERS = {
    "User-Agent": USER_AGENT,
    "Origin": "https://floridalottery.com",
    "Referer": "https://floridalottery.com/",
    "x-partner": "web",
}
LIST_HEADERS = {"User-Agent": USER_AGENT}

REQUEST_TIMEOUT = 20


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def list_games(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Return the active-game list. Each item: {id, name, price, topPrize, ...}."""
    s = session or make_session()
    r = s.get(LIST_URL, headers=LIST_HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    return payload.get("data", [])


def list_top_remaining(session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Authoritative list of currently-active games (those still being sold).

    Each item: {Id, GameName, TicketPrice, TopPrizes}. TopPrizes may be the
    string 'null' when the game's top prizes are exhausted.
    """
    s = session or make_session()
    r = s.get(TOP_REMAINING_URL, headers=DETAIL_HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_detail(
    game_id: str | int,
    session: requests.Session | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """Fetch a single game's detail (tiers + remaining counts).

    Raises requests.HTTPError after exhausting retries.
    """
    s = session or make_session()
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = s.get(
                DETAIL_URL,
                params={"id": str(game_id)},
                headers=DETAIL_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(2.0)
    assert last_err is not None
    raise last_err


def jitter_sleep(base: float = 1.0, spread: float = 0.5) -> None:
    """Sleep base + uniform(0, spread) seconds. Polite throttling between detail calls."""
    time.sleep(base + random.uniform(0, spread))
