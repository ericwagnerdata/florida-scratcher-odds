import json
from pathlib import Path

from fl_scratchers.ev import compute
from fl_scratchers.parse import parse_detail

FIXTURES = Path(__file__).parent / "fixtures"


def test_ev_against_fixture():
    """Sanity-check EV math on the saved 'THE PERFECT GIFT' fixture (#7028, $20).

    We don't lock in an exact EV — we assert it's plausible: positive remaining
    value, both estimators produce something, EV per ticket is in (0, ticket_price * 5).
    """
    payload = json.loads((FIXTURES / "game_7028.json").read_text(encoding="utf-8"))
    g = parse_detail(payload)
    r = compute(g)

    assert r.total_remaining_value > 0
    assert r.est_via_tiers is not None and r.est_via_tiers > 0
    assert r.est_via_overall is not None and r.est_via_overall > 0
    assert r.ev_per_ticket is not None
    assert 0 < r.ev_per_ticket < float(g.ticket_price) * 5
    # ev_minus_price should equal ev_per_ticket - 20
    assert abs(r.ev_minus_price - (r.ev_per_ticket - 20)) < 1e-6


def test_no_estimator_when_zero_remaining():
    """A game with all prizes claimed should flag rather than crash."""
    from decimal import Decimal
    from datetime import date
    from fl_scratchers.parse import Game, Tier

    g = Game(
        game_id=1,
        name="dummy",
        ticket_price=Decimal("5"),
        overall_odds=4.0,
        launch_date=date(2024, 1, 1),
        end_date=None,
        redemption_date=None,
        tiers=[Tier(Decimal("100"), 1000, 10, 0, 10)],
    )
    r = compute(g)
    assert r.ev_per_ticket is None
    assert r.sanity_flag == "no_estimator"
