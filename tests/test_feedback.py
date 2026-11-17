import sqlite3
from datetime import datetime, timezone

import pytest

from src import feedback
from src.ranking import rank_accounts
from src.scoring import TypeScore
from tests.conftest import make_account


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    feedback.init_db(c)
    yield c
    c.close()


def _scores(ids):
    return {a: {"x": TypeScore("x", 1.0, False, ())} for a in ids}


def test_record_and_read_back(conn):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    feedback.record_feedback(conn, "A0001", "O01", "taken", "called them", created_at=ts)
    row = conn.execute(
        "SELECT account_id, owner_id, action, note, created_at FROM feedback").fetchone()
    assert row == ("A0001", "O01", "taken", "called them", ts.isoformat())


def test_invalid_action_rejected(conn):
    with pytest.raises(ValueError):
        feedback.record_feedback(conn, "A0001", "O01", "snoozed")
    with pytest.raises(sqlite3.IntegrityError):  # DB constraint as a second line of defence
        conn.execute("INSERT INTO feedback (account_id, owner_id, action, created_at) "
                     "VALUES ('A1', 'O1', 'bogus', 'x')")


@pytest.mark.parametrize("action", ["taken", "not_applicable"])
def test_feedback_excludes_account_from_ranking(conn, action):
    accounts = [make_account(a) for a in ["A0001", "A0002", "A0003", "A0004"]]
    scores = _scores([a.account_id for a in accounts])
    before = rank_accounts(accounts, scores, top_n=3, min_value=0)["O01"]
    assert "A0001" in [r.account_id for r in before]

    feedback.record_feedback(conn, "A0001", "O01", action)
    after = rank_accounts(accounts, scores, top_n=3, min_value=0,
                          excluded=feedback.excluded_accounts(conn))["O01"]
    ids = [r.account_id for r in after]
    assert "A0001" not in ids
    assert ids == ["A0002", "A0003", "A0004"]  # backfilled from the next candidate


def test_exclusion_applies_across_owners(conn):
    feedback.record_feedback(conn, "A0001", "O99", "not_applicable")
    accounts = [make_account("A0001", owner_id="O01")]
    ranked = rank_accounts(accounts, _scores(["A0001"]), top_n=3, min_value=0,
                           excluded=feedback.excluded_accounts(conn))
    assert ranked == {"O01": []}


def test_exclusion_persists_across_connections(tmp_path):
    db = tmp_path / "nbc.sqlite"
    c1 = feedback.connect(db)
    feedback.record_feedback(c1, "A0007", "O01", "taken")
    c1.close()
    c2 = feedback.connect(db)  # re-applying schema must not wipe data
    assert feedback.excluded_accounts(c2) == {"A0007"}
    c2.close()
