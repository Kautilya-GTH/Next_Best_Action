import math

import pytest

from src.ingest import load_config
from src.scoring import score_account
from tests.conftest import EXAMPLE_CONFIG, make_account

RICH = {"gate_a": "true", "gate_b": "true", "flag": "true", "amount": "500000"}


@pytest.mark.parametrize("otype,gate", [("alpha", "gate_a"), ("beta", "gate_b")])
@pytest.mark.parametrize("closed_value", ["false", "0", None])
def test_gated_off_type_scores_exactly_zero(small_config, otype, gate, closed_value):
    signals = dict(RICH)
    if closed_value is None:
        del signals[gate]           # missing gate counts as false
    else:
        signals[gate] = closed_value
    scores = score_account(make_account(arr=900_000.0, days_to_renewal=1), signals, small_config)
    assert scores[otype].score == 0.0
    assert scores[otype].gated_off is True
    assert scores[otype].contributions == ()


def test_gate_open_scores_normally(small_config):
    scores = score_account(make_account(arr=200_000.0, days_to_renewal=60), RICH, small_config)
    assert math.isclose(scores["alpha"].score, 2.0 * 1.0 + 1.0 * 0.5)
    assert math.isclose(scores["beta"].score, 0.5 * 2.0 + 5.0 * 1.0)


def test_ungated_type_unaffected(small_config):
    scores = score_account(make_account(usage_score=80.0), {}, small_config)
    assert math.isclose(scores["gamma"].score, 0.8)


def test_every_example_gate_zeroes_its_type():
    config = load_config(EXAMPLE_CONFIG)
    all_true = {g: "true" for g in config.gates.values() if g}
    rich = {**all_true, "open_pipeline_amount": "75000", "feature_adoption_pct": "90",
            "support_escalation": "true"}
    acc = make_account(arr=150_000.0, days_to_renewal=10, usage_score=90.0)
    for otype, gate in config.gates.items():
        if gate is None:
            continue
        assert score_account(acc, rich, config)[otype].score > 0
        closed = {**rich, gate: "false"}
        assert score_account(acc, closed, config)[otype].score == 0.0
