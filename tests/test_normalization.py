import math

import pytest

from src.ingest import account_signal_values
from src.scoring import normalize, parse_bool, score_account
from tests.conftest import make_account

K = 30.0


@pytest.mark.parametrize("raw,expected", [
    ("true", 1.0), ("FALSE", 0.0), ("1", 1.0), ("0", 0.0), (None, 0.0),
])
def test_bool(raw, expected):
    assert normalize(raw, "bool", K) == expected


def test_bool_garbage_raises():
    with pytest.raises(ValueError):
        parse_bool("maybe")


def test_money_and_percent():
    assert normalize("100000", "money", K) == 1.0
    assert normalize("250000", "money", K) == 2.5
    assert normalize("75", "percent", K) == 0.75


@pytest.mark.parametrize("kind", ["money", "percent", "bool"])
def test_zero_values(kind):
    assert normalize("0", kind, K) == 0.0


@pytest.mark.parametrize("kind", ["bool", "money", "percent", "renewal"])
def test_missing_is_zero(kind):
    assert normalize(None, kind, K) == 0.0


@pytest.mark.parametrize("days,expected", [
    (-10, 1.0),   # overdue -> capped at 1
    (0, 1.0),     # due today -> 1 (no division by zero)
    (15, 1.0),    # K/days = 2 -> capped at 1
    (30, 1.0),
    (60, 0.5),
    (300, 0.1),
])
def test_renewal_inverse_with_cap(days, expected):
    assert math.isclose(normalize(str(days), "renewal", K), expected)


def test_seat_utilization_zero_seats_and_cap():
    assert make_account(seats_purchased=0, active_users=5).seat_utilization == 0.0
    assert make_account(seats_purchased=None).seat_utilization == 0.0
    assert make_account(seats_purchased=10, active_users=25).seat_utilization == 100.0
    assert make_account(seats_purchased=20, active_users=5).seat_utilization == 25.0


def test_missing_account_fields_become_missing_signals():
    values = account_signal_values(make_account(arr=None, days_to_renewal=None), {})
    assert values["arr"] is None and values["days_to_renewal"] is None


def test_missing_signals_score_zero_contribution(small_config):
    # gate_a true, but flag missing and arr missing -> alpha scores 0 (not gated, just empty)
    acc = make_account(arr=None)
    scores = score_account(acc, {"gate_a": "true"}, small_config)
    assert scores["alpha"].score == 0.0
    assert scores["alpha"].gated_off is False


def test_disabled_rule_ignored(small_config):
    acc = make_account(usage_score=40.0, arr=1_000_000.0)
    assert math.isclose(score_account(acc, {}, small_config)["gamma"].score, 0.4)


def test_money_uncapped_by_default():
    assert normalize("500000", "money", K) == 5.0
    assert normalize("500000", "money", K, money_cap=None) == 5.0


@pytest.mark.parametrize("raw,expected", [
    ("50000", 0.5), ("100000", 1.0), ("250000", 1.0), ("0", 0.0), (None, 0.0),
])
def test_money_cap(raw, expected):
    assert normalize(raw, "money", K, money_cap=1.0) == expected


def test_money_cap_only_affects_money():
    assert normalize("150", "percent", K, money_cap=1.0) == 1.5
    assert normalize("-5", "renewal", K, money_cap=1.0) == 1.0


def test_money_cap_applies_in_scoring(small_config):
    import dataclasses
    acc = make_account(arr=300_000.0)
    sig = {"gate_a": "true"}
    assert math.isclose(score_account(acc, sig, small_config)["alpha"].score, 3.0)
    capped = dataclasses.replace(small_config, money_cap=1.0)
    assert math.isclose(score_account(acc, sig, capped)["alpha"].score, 1.0)
