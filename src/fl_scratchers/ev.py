"""Expected-value math. Two estimators for tickets remaining; sanity flag if they diverge."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import Decimal

from .parse import Game


SANITY_DIVERGENCE = 0.15  # 15%


@dataclass(frozen=True)
class EVResult:
    ev_per_ticket: float | None
    ev_minus_price: float | None
    est_tickets_remaining: float | None
    est_via_tiers: float | None
    est_via_overall: float | None
    sanity_flag: str | None
    top_prize_remaining: int
    total_remaining_value: float


def _tier_estimator(game: Game) -> float | None:
    """Median of (total_printed × odds_1_in × fraction_remaining_at_tier).

    Each tier independently estimates total tickets remaining; we take the
    median to be robust against weird tiers (e.g. exhausted top prizes).
    """
    per_tier: list[float] = []
    for t in game.tiers:
        if t.total_printed <= 0:
            continue
        original_total_tickets = t.total_printed * t.odds_1_in
        frac_remaining = t.remaining / t.total_printed
        per_tier.append(original_total_tickets * frac_remaining)
    if not per_tier:
        return None
    return float(statistics.median(per_tier))


def _overall_estimator(game: Game) -> float | None:
    """Σ remaining × overall_odds. (Each remaining prize implies overall_odds tickets.)

    This is loose but useful as a cross-check.
    """
    if game.overall_odds <= 0:
        return None
    total_remaining = sum(t.remaining for t in game.tiers)
    if total_remaining <= 0:
        return None
    return float(total_remaining * game.overall_odds)


def compute(game: Game) -> EVResult:
    total_remaining_value = float(
        sum(Decimal(t.remaining) * t.prize_amount for t in game.tiers)
    )
    top_prize_remaining = game.tiers[0].remaining if game.tiers else 0

    est_tiers = _tier_estimator(game)
    est_overall = _overall_estimator(game)

    candidates = [e for e in (est_tiers, est_overall) if e and e > 0]
    if not candidates:
        return EVResult(
            ev_per_ticket=None,
            ev_minus_price=None,
            est_tickets_remaining=None,
            est_via_tiers=est_tiers,
            est_via_overall=est_overall,
            sanity_flag="no_estimator",
            top_prize_remaining=top_prize_remaining,
            total_remaining_value=total_remaining_value,
        )

    sanity = None
    if len(candidates) == 2:
        lo, hi = min(candidates), max(candidates)
        if (hi - lo) / hi > SANITY_DIVERGENCE:
            sanity = f"estimators_diverge({lo:.0f}_vs_{hi:.0f})"

    # Prefer the tier-based estimator when both available; it's per-tier evidence.
    est_remaining = est_tiers if est_tiers else est_overall
    assert est_remaining and est_remaining > 0

    ev_per_ticket = total_remaining_value / est_remaining
    ev_minus_price = ev_per_ticket - float(game.ticket_price)

    return EVResult(
        ev_per_ticket=ev_per_ticket,
        ev_minus_price=ev_minus_price,
        est_tickets_remaining=est_remaining,
        est_via_tiers=est_tiers,
        est_via_overall=est_overall,
        sanity_flag=sanity,
        top_prize_remaining=top_prize_remaining,
        total_remaining_value=total_remaining_value,
    )
