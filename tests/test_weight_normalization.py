import math

import yaml

from src.ingest import Rule, load_config, normalize_rule_weights
from src.scoring import score_account
from tests.conftest import EXAMPLE_CONFIG, make_account


def _sums(rules):
    out = {}
    for r in rules:
        if r.enabled:
            out[r.opportunity_type] = out.get(r.opportunity_type, 0.0) + abs(r.weight)
    return out


def test_enabled_weights_sum_to_one_per_type():
    rules = normalize_rule_weights([
        Rule("a", "x", 2.0, True), Rule("a", "y", 6.0, True),
        Rule("b", "x", 0.5, True),
    ])
    assert [r.weight for r in rules] == [0.25, 0.75, 1.0]
    assert all(math.isclose(v, 1.0) for v in _sums(rules).values())


def test_relative_importance_within_type_preserved():
    a, b = normalize_rule_weights([Rule("t", "x", 1.0, True), Rule("t", "y", 3.0, True)])
    assert math.isclose(b.weight / a.weight, 3.0)


def test_disabled_rules_excluded_from_total_and_untouched():
    rules = normalize_rule_weights([Rule("t", "x", 1.0, True), Rule("t", "y", 9.0, False)])
    assert rules[0].weight == 1.0
    assert rules[1].weight == 9.0


def test_negative_weights_normalized_by_absolute_sum():
    rules = normalize_rule_weights([Rule("t", "x", 3.0, True), Rule("t", "y", -1.0, True)])
    assert [r.weight for r in rules] == [0.75, -0.25]


def test_all_zero_weights_left_unchanged():
    rules = normalize_rule_weights([Rule("t", "x", 0.0, True)])
    assert rules[0].weight == 0.0


def test_example_config_is_normalized():
    config = load_config(EXAMPLE_CONFIG)
    assert config.normalize_weights is True
    assert all(math.isclose(v, 1.0) for v in _sums(config.rules).values())


def test_flag_off_keeps_raw_weights(tmp_path):
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw["normalize_weights"] = False
    path = tmp_path / "w.yaml"
    path.write_text(yaml.safe_dump(raw))
    config = load_config(path)
    assert [r.weight for r in config.rules] == [r["weight"] for r in raw["rules"]]


def test_types_share_a_common_ceiling():
    """With every signal maxed out (money at 1.0 = 100k), each open type scores 1.0."""
    config = load_config(EXAMPLE_CONFIG)
    signals = {"has_budget_signal": "true", "in_renewal_window": "true",
               "has_exec_sponsor": "true", "support_escalation": "true",
               "open_pipeline_amount": "100000", "feature_adoption_pct": "100"}
    acc = make_account(arr=100_000.0, days_to_renewal=1, usage_score=100.0,
                       active_users=10, seats_purchased=10)
    scores = score_account(acc, signals, config)
    for otype in config.opportunity_types:
        assert math.isclose(scores[otype].score, 1.0), otype


def _config_with(tmp_path, **overrides):
    raw = yaml.safe_load(EXAMPLE_CONFIG.read_text())
    raw.update(overrides)
    path = tmp_path / "w.yaml"
    path.write_text(yaml.safe_dump(raw))
    return load_config(path)


def test_example_config_values():
    config = load_config(EXAMPLE_CONFIG)
    assert config.renewal_k == 60
    assert config.money_cap is None


def test_money_cap_loaded_from_yaml(tmp_path):
    assert _config_with(tmp_path, money_cap=1.0).money_cap == 1.0


def test_invalid_money_cap_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        _config_with(tmp_path, money_cap=0)
