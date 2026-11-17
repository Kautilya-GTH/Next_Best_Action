"""Load accounts, signals and scoring config from disk into plain dataclasses."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

KINDS = {"bool", "money", "percent", "renewal"}

# Signals derived from accounts.csv columns (available to rules like any other signal).
ACCOUNT_SIGNALS = ("arr", "usage_score", "days_to_renewal", "seat_utilization")

RawValue = str | None  # raw CSV text; None when missing/blank


@dataclass(frozen=True)
class Account:
    account_id: str
    owner_id: str
    arr: float | None
    days_to_renewal: float | None
    usage_score: float | None
    active_users: int | None
    seats_purchased: int | None
    region: str

    @property
    def seat_utilization(self) -> float:
        """Percent of purchased seats in use, capped at 100; 0 when seats are 0/missing."""
        if not self.seats_purchased or self.seats_purchased <= 0 or self.active_users is None:
            return 0.0
        return min(100.0, 100.0 * self.active_users / self.seats_purchased)


@dataclass(frozen=True)
class Rule:
    opportunity_type: str
    signal_name: str
    weight: float
    enabled: bool


@dataclass(frozen=True)
class Config:
    min_value: float
    renewal_k: float
    money_cap: float | None
    top_n: int
    normalize_weights: bool
    signal_kinds: dict[str, str]
    gates: dict[str, str | None]  # opportunity_type -> gate signal (None = ungated)
    rules: tuple[Rule, ...] = field(default_factory=tuple)

    @property
    def opportunity_types(self) -> list[str]:
        return list(self.gates)


def _opt_float(text: str | None) -> float | None:
    return None if text is None or text.strip() == "" else float(text)


def _opt_int(text: str | None) -> int | None:
    return None if text is None or text.strip() == "" else int(float(text))


def load_accounts(path: Path) -> list[Account]:
    """Read accounts.csv. Raises ValueError on duplicate account_id."""
    accounts: list[Account] = []
    seen: set[str] = set()
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aid = row["account_id"].strip()
            if aid in seen:
                raise ValueError(f"duplicate account_id in accounts.csv: {aid}")
            seen.add(aid)
            accounts.append(Account(
                account_id=aid,
                owner_id=row["owner_id"].strip(),
                arr=_opt_float(row.get("arr")),
                days_to_renewal=_opt_float(row.get("days_to_renewal")),
                usage_score=_opt_float(row.get("usage_score")),
                active_users=_opt_int(row.get("active_users")),
                seats_purchased=_opt_int(row.get("seats_purchased")),
                region=(row.get("region") or "").strip(),
            ))
    return accounts


def load_signals(path: Path) -> dict[str, dict[str, RawValue]]:
    """Read signals.csv into {account_id: {signal_name: raw_value}}.

    Raises ValueError on a duplicate (account_id, signal_name) pair.
    """
    out: dict[str, dict[str, RawValue]] = {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aid, name = row["account_id"].strip(), row["signal_name"].strip()
            bucket = out.setdefault(aid, {})
            if name in bucket:
                raise ValueError(f"duplicate signal {name!r} for account {aid}")
            value = row.get("value")
            bucket[name] = None if value is None or value.strip() == "" else value.strip()
    return out


def load_config(path: Path) -> Config:
    """Parse and validate weights YAML."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    kinds: dict[str, str] = dict(raw.get("signals") or {})
    for name, kind in kinds.items():
        if kind not in KINDS:
            raise ValueError(f"signal {name!r} has unknown kind {kind!r}")

    gates: dict[str, str | None] = {}
    for otype, spec in (raw.get("opportunity_types") or {}).items():
        gate = (spec or {}).get("gate")
        if gate is not None and kinds.get(gate) != "bool":
            raise ValueError(f"gate {gate!r} for {otype!r} must be a declared bool signal")
        gates[otype] = gate

    rules = []
    for r in raw.get("rules") or []:
        rule = Rule(
            opportunity_type=str(r["opportunity_type"]),
            signal_name=str(r["signal_name"]),
            weight=float(r["weight"]),
            enabled=bool(r.get("enabled", True)),
        )
        if rule.opportunity_type not in gates:
            raise ValueError(f"rule references undeclared type {rule.opportunity_type!r}")
        if rule.signal_name not in kinds:
            raise ValueError(f"rule references undeclared signal {rule.signal_name!r}")
        rules.append(rule)

    normalize = bool(raw.get("normalize_weights", True))
    money_cap = raw.get("money_cap")
    if money_cap is not None:
        money_cap = float(money_cap)
        if money_cap <= 0:
            raise ValueError(f"money_cap must be positive or null, got {money_cap}")
    return Config(
        min_value=float(raw["min_value"]),
        renewal_k=float(raw["renewal_k"]),
        money_cap=money_cap,
        top_n=int(raw.get("top_n", 3)),
        normalize_weights=normalize,
        signal_kinds=kinds,
        gates=gates,
        rules=tuple(normalize_rule_weights(rules) if normalize else rules),
    )


def normalize_rule_weights(rules: list[Rule]) -> list[Rule]:
    """Rescale enabled weights so they sum (in absolute value) to 1 within each type.

    This puts every opportunity type on the same scale, so a type can't win just
    because its weights add up to more. Disabled rules keep their original weight
    and are ignored. A type whose enabled weights are all 0 is left unchanged.
    """
    totals: dict[str, float] = {}
    for r in rules:
        if r.enabled:
            totals[r.opportunity_type] = totals.get(r.opportunity_type, 0.0) + abs(r.weight)
    out = []
    for r in rules:
        total = totals.get(r.opportunity_type, 0.0)
        if r.enabled and total > 0:
            r = Rule(r.opportunity_type, r.signal_name, r.weight / total, r.enabled)
        out.append(r)
    return out


def account_signal_values(
    account: Account, signals: dict[str, RawValue]
) -> dict[str, RawValue]:
    """Merge accounts.csv-derived signals with signals.csv values for one account.

    signals.csv takes precedence if it defines a name that collides.
    """
    derived: dict[str, RawValue] = {
        "arr": None if account.arr is None else repr(account.arr),
        "usage_score": None if account.usage_score is None else repr(account.usage_score),
        "days_to_renewal": (
            None if account.days_to_renewal is None else repr(account.days_to_renewal)
        ),
        "seat_utilization": repr(account.seat_utilization),
    }
    return {**derived, **signals}


def load_into_db(
    conn: sqlite3.Connection,
    accounts: list[Account],
    signals: dict[str, dict[str, RawValue]],
) -> None:
    """Replace the accounts/signals tables with the given data (for SQL inspection)."""
    conn.execute("DELETE FROM accounts")
    conn.execute("DELETE FROM signals")
    conn.executemany(
        "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(a.account_id, a.owner_id, a.arr, a.days_to_renewal, a.usage_score,
          a.active_users, a.seats_purchased, a.region) for a in accounts],
    )
    conn.executemany(
        "INSERT INTO signals VALUES (?, ?, ?)",
        [(aid, name, value) for aid, sig in sorted(signals.items())
         for name, value in sorted(sig.items())],
    )
    conn.commit()
