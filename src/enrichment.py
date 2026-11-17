"""Template-based explanation text. No LLM calls, no network."""

from __future__ import annotations

from src.ingest import Account
from src.ranking import RankedRow

# PLACEHOLDER wording; one template per opportunity type.
TEMPLATES: dict[str, str] = {
    "expansion": (
        "Expansion candidate: {seat_utilization:.0f}% of {seats} seats in use, "
        "ARR ${arr:,.0f}."
    ),
    "renewal": (
        "Renewal focus: renews in {days} days, ARR ${arr:,.0f}."
    ),
    "adoption": (
        "Adoption play: usage score {usage:.0f}/100, {active} active users."
    ),
}
DEFAULT_TEMPLATE = "{otype} opportunity, ARR ${arr:,.0f}."  # PLACEHOLDER
TOP_DRIVERS = 2


def _fmt_days(days: float | None) -> str:
    return "unknown" if days is None else str(int(days))


def explain(row: RankedRow, account: Account) -> str:
    """One-line explanation for a ranked row, plus its top contributing signals."""
    template = TEMPLATES.get(row.best_type, DEFAULT_TEMPLATE)
    text = template.format(
        otype=row.best_type,
        arr=account.arr or 0.0,
        seats=account.seats_purchased or 0,
        seat_utilization=account.seat_utilization,
        days=_fmt_days(account.days_to_renewal),
        usage=account.usage_score or 0.0,
        active=account.active_users or 0,
    )
    drivers = sorted(row.type_score.contributions, key=lambda c: (-c[1], c[0]))[:TOP_DRIVERS]
    drivers = [d for d in drivers if d[1] > 0]
    if drivers:
        text += " Top drivers: " + ", ".join(f"{n} (+{v:.2f})" for n, v in drivers) + "."
    return text
