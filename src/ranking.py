"""Priority computation, filtering, dedup and per-owner top-N selection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.ingest import Account
from src.scoring import TypeScore

PRIORITY_WEIGHTS = (1.0, 0.3, 0.1)  # from spec: top + 0.3*second + 0.1*third


def priority(scores: Iterable[float]) -> float:
    """top + 0.3*second + 0.1*third over the account's type scores (missing -> 0)."""
    ordered = sorted(scores, reverse=True)[: len(PRIORITY_WEIGHTS)]
    return sum(w * s for w, s in zip(PRIORITY_WEIGHTS, ordered, strict=False))


@dataclass(frozen=True)
class RankedRow:
    owner_id: str
    account_id: str
    rank: int
    best_type: str
    best_score: float
    priority: float
    type_score: TypeScore


def best_type(type_scores: dict[str, TypeScore]) -> TypeScore:
    """Highest-scoring type; ties broken by type name ascending for determinism."""
    return min(type_scores.values(), key=lambda ts: (-ts.score, ts.opportunity_type))


def rank_accounts(
    accounts: list[Account],
    scores: dict[str, dict[str, TypeScore]],
    *,
    top_n: int,
    min_value: float,
    excluded: set[str] | frozenset[str] = frozenset(),
) -> dict[str, list[RankedRow]]:
    """Return {owner_id: [RankedRow, ...]} with at most top_n rows per owner.

    Steps: drop excluded accounts and accounts with arr < min_value (missing arr
    counts as 0), compute priority, keep one row per account (best type only),
    sort by priority desc then account_id asc, take top_n per owner.
    Every owner present in `accounts` gets a key, possibly with an empty list.
    """
    candidates: dict[str, dict[str, tuple[float, TypeScore]]] = {}
    owners: set[str] = set()
    for acc in accounts:
        owners.add(acc.owner_id)
        if acc.account_id in excluded:
            continue
        if (acc.arr or 0.0) < min_value:
            continue
        type_scores = scores[acc.account_id]
        if not type_scores:
            continue
        prio = priority(ts.score for ts in type_scores.values())
        # Dedup: keyed by account_id, so an account yields at most one row.
        candidates.setdefault(acc.owner_id, {})[acc.account_id] = (
            prio, best_type(type_scores))

    result: dict[str, list[RankedRow]] = {}
    for owner_id in sorted(owners):
        rows = sorted(candidates.get(owner_id, {}).items(), key=lambda kv: (-kv[1][0], kv[0]))
        result[owner_id] = [
            RankedRow(owner_id, aid, i, ts.opportunity_type, ts.score, prio, ts)
            for i, (aid, (prio, ts)) in enumerate(rows[:top_n], start=1)
        ]
    return result
