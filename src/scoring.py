"""Normalization and per-type scoring.

score(account, type) = sum(normalize(value) * weight) over enabled rules,
or exactly 0.0 if the type's gate signal is false or missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ingest import Account, Config, RawValue, account_signal_values

MONEY_SCALE = 100_000.0   # from spec: money -> value / 100000
PERCENT_SCALE = 100.0     # from spec: percent -> value / 100

_TRUE = {"true", "1", "yes", "y", "t"}
_FALSE = {"false", "0", "no", "n", "f"}


def parse_bool(raw: RawValue) -> bool:
    """Parse a raw bool. Missing -> False. Raises ValueError on unrecognised text."""
    if raw is None:
        return False
    text = raw.strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        raise ValueError(f"cannot parse bool from {raw!r}") from None


def normalize(
    raw: RawValue, kind: str, renewal_k: float, money_cap: float | None = None
) -> float:
    """Normalize a raw signal value to a float. Missing values normalize to 0.0.

    bool    -> 1.0 / 0.0
    money   -> value / 100000, then min(money_cap, ...) when money_cap is set
    percent -> value / 100
    renewal -> 1.0 if days <= 0 else min(1, renewal_k / days)
    """
    if raw is None:
        return 0.0
    if kind == "bool":
        return 1.0 if parse_bool(raw) else 0.0
    value = float(raw)
    if kind == "money":
        scaled = value / MONEY_SCALE
        return scaled if money_cap is None else min(money_cap, scaled)
    if kind == "percent":
        return value / PERCENT_SCALE
    if kind == "renewal":
        if value <= 0:
            return 1.0
        return min(1.0, renewal_k / value)
    raise ValueError(f"unknown kind {kind!r}")


@dataclass(frozen=True)
class TypeScore:
    opportunity_type: str
    score: float
    gated_off: bool
    contributions: tuple[tuple[str, float], ...]  # (signal_name, normalized*weight)


def score_type(values: dict[str, RawValue], otype: str, config: Config) -> TypeScore:
    """Score one opportunity type from an account's merged raw signal values."""
    gate = config.gates[otype]
    if gate is not None and not parse_bool(values.get(gate)):
        return TypeScore(otype, 0.0, True, ())
    contributions = []
    for rule in config.rules:
        if rule.opportunity_type != otype or not rule.enabled:
            continue
        norm = normalize(values.get(rule.signal_name), config.signal_kinds[rule.signal_name],
                         config.renewal_k, config.money_cap)
        contributions.append((rule.signal_name, norm * rule.weight))
    return TypeScore(otype, sum(c for _, c in contributions), False, tuple(contributions))


def score_account(
    account: Account, signals: dict[str, RawValue], config: Config
) -> dict[str, TypeScore]:
    """Score every configured opportunity type for one account."""
    values = account_signal_values(account, signals)
    return {otype: score_type(values, otype, config) for otype in config.opportunity_types}


def score_all(
    accounts: list[Account],
    signals: dict[str, dict[str, RawValue]],
    config: Config,
) -> dict[str, dict[str, TypeScore]]:
    """{account_id: {opportunity_type: TypeScore}} for all accounts."""
    return {a.account_id: score_account(a, signals.get(a.account_id, {}), config)
            for a in accounts}
