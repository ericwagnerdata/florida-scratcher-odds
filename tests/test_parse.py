import json
from decimal import Decimal
from datetime import date
from pathlib import Path

from fl_scratchers.parse import (
    parse_detail,
    parse_money,
    parse_odds,
    parse_date,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_money():
    assert parse_money("$5,000.00") == Decimal("5000.00")
    assert parse_money(" $5,000,000.00 ") == Decimal("5000000.00")
    assert parse_money("$20") == Decimal("20")


def test_parse_odds():
    assert parse_odds("1-in-76497") == 76497
    assert parse_odds("1-in-3,000,000") == 3000000


def test_parse_date():
    assert parse_date("2024-10-28 00:00:00") == date(2024, 10, 28)
    assert parse_date("2024-10-28") == date(2024, 10, 28)
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_detail_fixture():
    g = parse_detail(load("game_7028.json"))
    assert g.game_id == 7028
    assert g.name == "THE PERFECT GIFT"
    assert g.ticket_price == Decimal("20")
    assert g.overall_odds == 2.79
    assert g.launch_date == date(2024, 10, 28)
    assert len(g.tiers) == 10

    top = g.tiers[0]
    assert top.prize_amount == Decimal("5000000.00")
    assert top.odds_1_in == 3000000
    assert top.total_printed == 4
    assert top.remaining == 2
    assert top.paid == 2
