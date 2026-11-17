"""Determinism, dedup-in-digest and feedback exclusion through the full CLI pipeline."""

import re
import shutil

from data.generate_dummy import write_dataset
from src import feedback, ingest, scoring
from src.cli import main, run_digest
from tests.conftest import EXAMPLE_CONFIG

ROW_RE = re.compile(r"^\| (\d+) \| (A\d{4}) \|", re.M)


def _pipeline(tmp_path, name, seed=42):
    data = tmp_path / name / "data"
    write_dataset(data, seed=seed)
    out = tmp_path / name / "out"
    paths = run_digest(data, EXAMPLE_CONFIG, tmp_path / name / "nbc.sqlite", out)
    return data, out, paths


def _read_tree(out):
    return {p.relative_to(out).as_posix(): p.read_text() for p in sorted(out.rglob("*.md"))}


def test_same_seed_identical_csvs_scores_and_digests(tmp_path):
    d1, o1, _ = _pipeline(tmp_path, "run1")
    d2, o2, _ = _pipeline(tmp_path, "run2")
    for f in ["accounts.csv", "signals.csv"]:
        assert (d1 / f).read_bytes() == (d2 / f).read_bytes()

    config = ingest.load_config(EXAMPLE_CONFIG)

    def scores(d):
        return scoring.score_all(ingest.load_accounts(d / "accounts.csv"),
                                 ingest.load_signals(d / "signals.csv"), config)

    assert scores(d1) == scores(d2)
    assert _read_tree(o1) == _read_tree(o2)
    assert _read_tree(o1)  # non-empty


def test_different_seed_changes_data(tmp_path):
    d1, _, _ = _pipeline(tmp_path, "a", seed=1)
    d2, _, _ = _pipeline(tmp_path, "b", seed=2)
    assert (d1 / "accounts.csv").read_bytes() != (d2 / "accounts.csv").read_bytes()


def test_digest_has_each_account_at_most_once_and_top_n(tmp_path):
    _, out, paths = _pipeline(tmp_path, "run")
    assert len(paths) == 5  # one per owner
    for p in paths:
        ids = [m.group(2) for m in ROW_RE.finditer(p.read_text())]
        assert len(ids) == len(set(ids))
        assert len(ids) <= 3


def test_feedback_removes_account_from_next_digest(tmp_path):
    data, out, paths = _pipeline(tmp_path, "run")
    db = tmp_path / "run" / "nbc.sqlite"
    first = ROW_RE.search(paths[0].read_text())
    assert first, "expected at least one account in the first owner's digest"
    victim, owner = first.group(2), paths[0].parent.name

    assert main(["feedback", "--db", str(db), "--account", victim,
                 "--owner", owner, "--action", "taken"]) == 0
    shutil.rmtree(out)
    run_digest(data, EXAMPLE_CONFIG, db, out)
    all_text = "".join(_read_tree(out).values())
    assert victim not in all_text

    conn = feedback.connect(db)
    assert victim in feedback.excluded_accounts(conn)
    conn.close()
