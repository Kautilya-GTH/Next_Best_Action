from __future__ import annotations

from pathlib import Path

import pytest

from src.ingest import Account, Config, Rule

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_CONFIG = ROOT / "config" / "weights.example.yaml"


def make_account(account_id: str = "A0001", owner_id: str = "O01", **kw) -> Account:
    defaults = dict(arr=50_000.0, days_to_renewal=120.0, usage_score=50.0,
                    active_users=10, seats_purchased=20, region="north")
    defaults.update(kw)
    return Account(account_id=account_id, owner_id=owner_id, **defaults)


@pytest.fixture
def small_config() -> Config:
    """Hand-built config with easy-to-verify weights (test-only values)."""
    return Config(
        min_value=0.0,
        renewal_k=30.0,
        money_cap=None,
        top_n=3,
        normalize_weights=False,  # raw weights keep hand-checked arithmetic simple
        signal_kinds={
            "arr": "money", "usage_score": "percent", "days_to_renewal": "renewal",
            "seat_utilization": "percent", "gate_a": "bool", "gate_b": "bool",
            "flag": "bool", "amount": "money",
        },
        gates={"alpha": "gate_a", "beta": "gate_b", "gamma": None},
        rules=(
            Rule("alpha", "arr", 1.0, True),
            Rule("alpha", "flag", 0.5, True),
            Rule("beta", "days_to_renewal", 2.0, True),
            Rule("beta", "amount", 1.0, True),
            Rule("gamma", "usage_score", 1.0, True),
            Rule("gamma", "arr", 100.0, False),  # disabled: must be ignored
        ),
    )
