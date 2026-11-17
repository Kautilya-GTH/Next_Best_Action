"""Owner feedback storage (SQLite). Any feedback on an account excludes it for all owners."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
ACTIONS = ("taken", "not_applicable")


def connect(db_path: Path | str, schema_path: Path = SCHEMA_PATH) -> sqlite3.Connection:
    """Open (or create) the database and apply the idempotent schema."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn, schema_path)
    return conn


def init_db(conn: sqlite3.Connection, schema_path: Path = SCHEMA_PATH) -> None:
    conn.executescript(Path(schema_path).read_text(encoding="utf-8"))
    conn.commit()


def record_feedback(
    conn: sqlite3.Connection,
    account_id: str,
    owner_id: str,
    action: str,
    note: str = "",
    created_at: datetime | None = None,
) -> None:
    """Insert one feedback row. Raises ValueError on an unknown action."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}, got {action!r}")
    ts = (created_at or datetime.now(timezone.utc)).isoformat()
    conn.execute(
        "INSERT INTO feedback (account_id, owner_id, action, note, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (account_id, owner_id, action, note, ts),
    )
    conn.commit()


def excluded_accounts(conn: sqlite3.Connection) -> set[str]:
    """Account IDs that must not appear in future digests."""
    return {row[0] for row in conn.execute("SELECT account_id FROM v_excluded_accounts")}
