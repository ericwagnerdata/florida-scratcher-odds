"""Pure parsing — JSON dict → normalized model. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Tier:
    prize_amount: Decimal
    odds_1_in: int
    total_printed: int
    remaining: int
    paid: int


@dataclass
class Game:
    game_id: int
    name: str
    ticket_price: Decimal
    overall_odds: float
    launch_date: date | None
    end_date: date | None
    redemption_date: date | None
    tiers: list[Tier] = field(default_factory=list)


_MONEY_RE = re.compile(r"[^\d.]")
_ODDS_RE = re.compile(r"1-in-([\d,.]+)", re.IGNORECASE)


def parse_money(s: str) -> Decimal:
    """'$5,000.00' → Decimal('5000.00'). Tolerates whitespace, commas, $."""
    cleaned = _MONEY_RE.sub("", s.strip())
    return Decimal(cleaned) if cleaned else Decimal("0")


def parse_odds(s: str) -> int:
    """'1-in-76497' → 76497. '1-in-3,000,000' also handled."""
    m = _ODDS_RE.search(s)
    if not m:
        raise ValueError(f"Unrecognized odds string: {s!r}")
    return int(m.group(1).replace(",", ""))


def parse_date(s: str | None) -> date | None:
    """'2024-10-28 00:00:00' → date(2024,10,28). Returns None on empty/invalid."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_detail(payload: dict[str, Any]) -> Game:
    """Normalize an APIM `getscratchinfo` response into a Game."""
    tiers = [
        Tier(
            prize_amount=parse_money(t["PrizeAmount"]),
            odds_1_in=parse_odds(t["WinningOdds"]),
            total_printed=int(t["TotalPrizes"]),
            remaining=int(t["PrizesRemaining"]),
            paid=int(t["PrizesPaid"]),
        )
        for t in payload.get("OddsTiers", [])
    ]
    return Game(
        game_id=int(payload["Id"]),
        name=str(payload["GameName"]).strip(),
        ticket_price=Decimal(str(payload["TicketPrice"])),
        overall_odds=float(payload["OverallOdds"]),
        launch_date=parse_date(payload.get("LaunchDate")),
        end_date=parse_date(payload.get("EndDate")),
        redemption_date=parse_date(payload.get("RedemptionDate")),
        tiers=tiers,
    )


def parse_list_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a list-endpoint card into a flat dict."""
    return {
        "game_id": int(item["id"]),
        "name": str(item.get("name", "")).strip(),
        "ticket_price": Decimal(str(item.get("price", 0))),
        "advertised_top_prize": str(item.get("topPrize", "")).strip(),
    }
