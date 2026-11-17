"""Seeded synthetic data generator.

Writes accounts.csv and signals.csv. Output depends only on (seed, n_accounts,
n_owners): the same arguments always produce byte-identical files.
All distributions and ranges below are PLACEHOLDER values.

Usage:
    python -m data.generate_dummy --seed 42 --out data/
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

DEFAULT_SEED = 42
DEFAULT_ACCOUNTS = 60          # PLACEHOLDER
DEFAULT_OWNERS = 5             # PLACEHOLDER
REGIONS = ["north", "south", "east", "west"]  # PLACEHOLDER

ACCOUNT_FIELDS = [
    "account_id", "owner_id", "arr", "days_to_renewal", "usage_score",
    "active_users", "seats_purchased", "region",
]
SIGNAL_FIELDS = ["account_id", "signal_name", "value"]

BOOL_SIGNALS = {                 # signal -> probability of true (PLACEHOLDER)
    "has_budget_signal": 0.5,
    "in_renewal_window": 0.4,
    "has_exec_sponsor": 0.6,
    "support_escalation": 0.2,
}
P_SIGNAL_MISSING = 0.05          # PLACEHOLDER: chance a signal row is omitted


def generate(
    seed: int = DEFAULT_SEED,
    n_accounts: int = DEFAULT_ACCOUNTS,
    n_owners: int = DEFAULT_OWNERS,
) -> tuple[list[dict], list[dict]]:
    """Return (accounts, signals) as lists of row dicts with string values."""
    rng = random.Random(seed)
    owners = [f"O{i:02d}" for i in range(1, n_owners + 1)]
    accounts: list[dict] = []
    signals: list[dict] = []

    for i in range(1, n_accounts + 1):
        account_id = f"A{i:04d}"
        seats = rng.choice([0] + [rng.randint(5, 500)] * 9)  # ~10% zero seats (edge case)
        active = rng.randint(0, int(seats * 1.2)) if seats else rng.randint(0, 5)
        accounts.append({
            "account_id": account_id,
            "owner_id": owners[(i - 1) % n_owners],
            "arr": str(rng.randint(0, 40) * 5000),             # 0 .. 200,000
            "days_to_renewal": str(rng.randint(-30, 400)),     # includes overdue
            "usage_score": str(rng.randint(0, 100)),
            "active_users": str(active),
            "seats_purchased": str(seats),
            "region": rng.choice(REGIONS),
        })

        candidate = []
        for name, p in BOOL_SIGNALS.items():
            candidate.append((name, "true" if rng.random() < p else "false"))
        candidate.append(("open_pipeline_amount", str(rng.randint(0, 30) * 2500)))
        candidate.append(("feature_adoption_pct", str(rng.randint(0, 100))))
        for name, value in candidate:
            if rng.random() < P_SIGNAL_MISSING:
                continue
            signals.append({"account_id": account_id, "signal_name": name, "value": value})

    return accounts, signals


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_dataset(
    out_dir: Path,
    seed: int = DEFAULT_SEED,
    n_accounts: int = DEFAULT_ACCOUNTS,
    n_owners: int = DEFAULT_OWNERS,
) -> tuple[Path, Path]:
    accounts, signals = generate(seed, n_accounts, n_owners)
    a_path, s_path = out_dir / "accounts.csv", out_dir / "signals.csv"
    write_csv(a_path, ACCOUNT_FIELDS, accounts)
    write_csv(s_path, SIGNAL_FIELDS, signals)
    return a_path, s_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--accounts", type=int, default=DEFAULT_ACCOUNTS)
    parser.add_argument("--owners", type=int, default=DEFAULT_OWNERS)
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    a_path, s_path = write_dataset(args.out, args.seed, args.accounts, args.owners)
    print(f"wrote {a_path} and {s_path}")


if __name__ == "__main__":
    main()
