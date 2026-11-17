"""Render and write per-owner digest.md files.

Output is deterministic: no timestamps, fixed ordering, fixed float formatting.
"""

from __future__ import annotations

from pathlib import Path

from src.enrichment import explain
from src.ingest import Account
from src.ranking import RankedRow


def render_digest(owner_id: str, rows: list[RankedRow], accounts: dict[str, Account]) -> str:
    lines = [f"# Account digest: {owner_id}", ""]
    if not rows:
        lines += ["_No accounts to review._", ""]
        return "\n".join(lines)
    lines += [
        "| Rank | Account | Opportunity | Score | Priority |",
        "|-----:|---------|-------------|------:|---------:|",
    ]
    for r in rows:
        lines.append(f"| {r.rank} | {r.account_id} | {r.best_type} | "
                     f"{r.best_score:.3f} | {r.priority:.3f} |")
    lines.append("")
    for r in rows:
        lines += [f"## {r.rank}. {r.account_id}: {r.best_type}", "",
                  explain(r, accounts[r.account_id]), ""]
    return "\n".join(lines)


def write_digests(
    ranked: dict[str, list[RankedRow]],
    accounts: list[Account],
    out_dir: Path,
) -> list[Path]:
    """Write out_dir/<owner_id>/digest.md for every owner. Returns paths written."""
    by_id = {a.account_id: a for a in accounts}
    paths = []
    for owner_id in sorted(ranked):
        path = Path(out_dir) / owner_id / "digest.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_digest(owner_id, ranked[owner_id], by_id), encoding="utf-8")
        paths.append(path)
    return paths
