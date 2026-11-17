import math

from src.ranking import priority, rank_accounts
from src.scoring import TypeScore
from tests.conftest import make_account


def ts_map(**scores: float) -> dict[str, TypeScore]:
    return {k: TypeScore(k, v, False, ()) for k, v in scores.items()}


def test_priority_formula():
    assert math.isclose(priority([0.5, 2.0, 1.0]), 2.0 + 0.3 * 1.0 + 0.1 * 0.5)


def test_priority_with_fewer_than_three_types():
    assert priority([]) == 0.0
    assert priority([1.0]) == 1.0
    assert math.isclose(priority([1.0, 2.0]), 2.0 + 0.3)


def test_priority_ignores_fourth_type():
    assert math.isclose(priority([4, 3, 2, 1]), 4 + 0.9 + 0.2)


def test_order_by_priority_then_account_id_tiebreak():
    accounts = [make_account(a) for a in ["A0003", "A0001", "A0002", "A0004"]]
    scores = {
        "A0003": ts_map(x=1.0, y=0.5),   # prio 1.15
        "A0001": ts_map(x=1.0, y=0.5),   # prio 1.15 (tie with A0003)
        "A0002": ts_map(x=2.0),          # prio 2.0
        "A0004": ts_map(x=0.1),
    }
    rows = rank_accounts(accounts, scores, top_n=3, min_value=0)["O01"]
    assert [r.account_id for r in rows] == ["A0002", "A0001", "A0003"]
    assert [r.rank for r in rows] == [1, 2, 3]


def test_tiebreak_is_independent_of_input_order():
    ids = ["A0005", "A0002", "A0009", "A0001"]
    scores = {a: ts_map(x=1.0) for a in ids}
    fwd = rank_accounts([make_account(a) for a in ids], scores, top_n=10, min_value=0)
    rev = rank_accounts([make_account(a) for a in reversed(ids)], scores, top_n=10, min_value=0)
    assert [r.account_id for r in fwd["O01"]] == ["A0001", "A0002", "A0005", "A0009"]
    assert fwd == rev


def test_top_n_per_owner():
    accounts = [make_account(f"A{i:04d}", owner_id=f"O0{i % 2}") for i in range(10)]
    scores = {a.account_id: ts_map(x=float(i)) for i, a in enumerate(accounts)}
    ranked = rank_accounts(accounts, scores, top_n=3, min_value=0)
    assert set(ranked) == {"O00", "O01"}
    assert all(len(rows) == 3 for rows in ranked.values())
    assert all(r.owner_id == owner for owner, rows in ranked.items() for r in rows)


def test_dedup_one_row_per_account_best_type_only():
    accounts = [make_account("A0001"), make_account("A0002")]
    scores = {"A0001": ts_map(alpha=0.9, beta=0.7, gamma=0.8),
              "A0002": ts_map(alpha=0.1)}
    rows = rank_accounts(accounts, scores, top_n=5, min_value=0)["O01"]
    ids = [r.account_id for r in rows]
    assert len(ids) == len(set(ids)) == 2
    assert rows[0].best_type == "alpha" and rows[0].best_score == 0.9


def test_best_type_tie_broken_by_name():
    rows = rank_accounts([make_account()], {"A0001": ts_map(zeta=1.0, beta=1.0)},
                         top_n=1, min_value=0)["O01"]
    assert rows[0].best_type == "beta"


def test_min_value_filters_on_arr():
    accounts = [make_account("A0001", arr=9_999.0), make_account("A0002", arr=10_000.0),
                make_account("A0003", arr=None)]
    scores = {a.account_id: ts_map(x=5.0) for a in accounts}
    rows = rank_accounts(accounts, scores, top_n=5, min_value=10_000)["O01"]
    assert [r.account_id for r in rows] == ["A0002"]


def test_owner_with_everything_filtered_gets_empty_list():
    ranked = rank_accounts([make_account(arr=0.0)], {"A0001": ts_map(x=1.0)},
                           top_n=3, min_value=1.0)
    assert ranked == {"O01": []}


def test_zero_score_accounts_fill_slots_when_owner_has_few_candidates():
    # Agreed rule: no score floor, so an owner with few accounts still gets a full digest.
    accounts = [make_account("A0001"), make_account("A0002")]
    scores = {"A0001": ts_map(x=0.7), "A0002": ts_map(x=0.0, y=0.0)}
    rows = rank_accounts(accounts, scores, top_n=3, min_value=0)["O01"]
    assert [r.account_id for r in rows] == ["A0001", "A0002"]
    assert rows[1].best_score == 0.0
