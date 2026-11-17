"""Command-line entry point.

    python -m src.cli generate --seed 42 --out data/
    python -m src.cli digest   --data data/ --config config/weights.example.yaml \
                               --db nbc.sqlite --out out/ [--top-n 3]
    python -m src.cli feedback --db nbc.sqlite --account A0001 --owner O01 \
                               --action taken [--note "..."]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from data.generate_dummy import DEFAULT_SEED, write_dataset
from src import feedback, ingest, ranking, scoring
from src.digest import write_digests


def run_digest(
    data_dir: Path, config_path: Path, db_path: Path, out_dir: Path, top_n: int | None = None
) -> list[Path]:
    """Full pipeline: ingest -> score -> exclude feedback -> rank -> write digests."""
    config = ingest.load_config(config_path)
    accounts = ingest.load_accounts(data_dir / "accounts.csv")
    signals = ingest.load_signals(data_dir / "signals.csv")
    conn = feedback.connect(db_path)
    try:
        ingest.load_into_db(conn, accounts, signals)
        excluded = feedback.excluded_accounts(conn)
    finally:
        conn.close()
    scores = scoring.score_all(accounts, signals, config)
    ranked = ranking.rank_accounts(
        accounts, scores,
        top_n=top_n if top_n is not None else config.top_n,
        min_value=config.min_value,
        excluded=excluded,
    )
    return write_digests(ranked, accounts, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nbc", description="Account prioritization MVP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write seeded synthetic CSVs")
    g.add_argument("--seed", type=int, default=DEFAULT_SEED)
    g.add_argument("--out", type=Path, default=Path("data"))

    d = sub.add_parser("digest", help="score, rank and write digest.md per owner")
    d.add_argument("--data", type=Path, default=Path("data"))
    d.add_argument("--config", type=Path, default=Path("config/weights.example.yaml"))
    d.add_argument("--db", type=Path, default=Path("nbc.sqlite"))
    d.add_argument("--out", type=Path, default=Path("out"))
    d.add_argument("--top-n", type=int, default=None)

    f = sub.add_parser("feedback", help="record owner feedback for an account")
    f.add_argument("--db", type=Path, default=Path("nbc.sqlite"))
    f.add_argument("--account", required=True)
    f.add_argument("--owner", required=True)
    f.add_argument("--action", required=True, choices=feedback.ACTIONS)
    f.add_argument("--note", default="")

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        for p in write_dataset(args.out, args.seed):
            print(f"wrote {p}")
    elif args.cmd == "digest":
        for p in run_digest(args.data, args.config, args.db, args.out, args.top_n):
            print(f"wrote {p}")
    elif args.cmd == "feedback":
        conn = feedback.connect(args.db)
        try:
            feedback.record_feedback(conn, args.account, args.owner, args.action, args.note)
        finally:
            conn.close()
        print(f"recorded {args.action} for {args.account}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
