# nbc-mvp: signal-based account prioritization

A small, deterministic engine. It scores accounts against several opportunity
types, ranks the top N per owner, writes a plain-text digest for each owner,
and records owner feedback so actioned accounts drop out of later digests.

All data is synthetic. Every opportunity type, signal name, weight and
threshold is a **PLACEHOLDER** to be replaced with your own values.

## Quick start

```bash
pip install -e ".[dev]"

python -m src.cli generate --seed 42 --out data/          # synthetic CSVs
python -m src.cli digest --data data/ \
    --config config/weights.example.yaml \
    --db out/nbc.sqlite --out out/ --top-n 3              # out/<owner_id>/digest.md

python -m src.cli feedback --db out/nbc.sqlite \
    --account A0021 --owner O01 --action taken --note "followed up"
python -m src.cli digest --db out/nbc.sqlite               # A0021 is now excluded

ruff check . && pytest -q
```

## Architecture

```
 data/generate_dummy.py (seeded)
          │
          ▼
 accounts.csv   signals.csv        config/weights.yaml
          │         │                     │
          └────┬────┘                     │
               ▼                          ▼
        src/ingest.py ──────────── load_config()
   Account, raw signals, Config
               │         └──────────► sql/schema.sql (SQLite: accounts, signals)
               ▼
        src/scoring.py
   normalize() → gate check → Σ(norm × weight) per type
               │
               ▼                     ┌──────────────────────────┐
        src/ranking.py ◄─────────────┤ src/feedback.py (SQLite) │◄── cli feedback
   exclude → MIN_VALUE(arr) →        │ feedback table           │
   priority → dedup → top-N/owner    │ v_excluded_accounts view │
               │                     └──────────────────────────┘
               ▼
        src/enrichment.py  (string templates, no LLM)
               │
               ▼
        src/digest.py  →  out/<owner_id>/digest.md
```

`src/cli.py` connects all the stages: `generate`, `digest` and `feedback`.

## Business rules

| Rule | Behaviour | Source |
|---|---|---|
| Score | `Σ normalize(value) × weight` over enabled rules | spec |
| Weight normalization | enabled weights are rescaled to sum (by absolute value) to 1 within each type, so every type scores on the same scale. Turn off with `normalize_weights: false` | decided |
| bool | true → 1, false → 0 | spec |
| money | `value / 100000`, optionally capped with `money_cap` (default `null` = no cap) | spec + decided |
| percent | `value / 100` | spec |
| renewal | `days ≤ 0 → 1`, else `min(1, K / days)`, K = 60 | decided; K is PLACEHOLDER |
| Gate | gate false **or missing** → type score is exactly 0 | spec + decided |
| Missing signal | contributes 0 | decided |
| Account-level signals | `arr`, `usage_score`, `days_to_renewal`, and `seat_utilization = min(100, active/seats × 100)`, which is 0 when seats = 0 | decided |
| MIN_VALUE | drop the account if `arr < min_value` (missing arr counts as 0) | decided; value is PLACEHOLDER |
| Priority | `top + 0.3·second + 0.1·third` of the type scores | spec |
| Order | priority desc, then `account_id` asc | spec |
| Best type tie | opportunity type name asc | implementation detail |
| Dedup | one row per account, best type only | spec |
| Score floor | none: an owner with few candidates still gets a full top N, even if some scores are 0 | decided |
| Feedback | any `taken` / `not_applicable` row excludes the account for **all** owners, permanently | spec + decided |

## Configuration (`config/weights.example.yaml`)

```yaml
min_value: 10000          # PLACEHOLDER
renewal_k: 60             # PLACEHOLDER
money_cap: null           # e.g. 1.0 caps money at 100k; null = no cap
normalize_weights: true   # rescale weights to sum to 1 per type
top_n: 3
signals:                  # signal_name -> bool | money | percent | renewal
  has_budget_signal: bool
opportunity_types:        # type -> gate (a bool signal, or omit for ungated)
  expansion: {gate: has_budget_signal}
rules:                    # the four spec fields
  - {opportunity_type: expansion, signal_name: seat_utilization, weight: 1.0, enabled: true}
```

## Module interfaces

```python
# src/ingest.py
@dataclass(frozen=True) class Account: account_id, owner_id, arr, days_to_renewal,
    usage_score, active_users, seats_purchased, region; seat_utilization -> float
@dataclass(frozen=True) class Rule: opportunity_type, signal_name, weight, enabled
@dataclass(frozen=True) class Config: min_value, renewal_k, top_n, signal_kinds, gates, rules
def load_accounts(path: Path) -> list[Account]
def load_signals(path: Path) -> dict[str, dict[str, str | None]]
def load_config(path: Path) -> Config
def account_signal_values(account: Account, signals: dict[str, str | None]) -> dict[str, str | None]
def load_into_db(conn: sqlite3.Connection, accounts: list[Account], signals: dict) -> None

# src/scoring.py
def parse_bool(raw: str | None) -> bool
def normalize(raw: str | None, kind: str, renewal_k: float) -> float
@dataclass(frozen=True) class TypeScore: opportunity_type, score, gated_off, contributions
def score_type(values: dict[str, str | None], otype: str, config: Config) -> TypeScore
def score_account(account: Account, signals: dict, config: Config) -> dict[str, TypeScore]
def score_all(accounts: list[Account], signals: dict, config: Config) -> dict[str, dict[str, TypeScore]]

# src/ranking.py
def priority(scores: Iterable[float]) -> float
@dataclass(frozen=True) class RankedRow: owner_id, account_id, rank, best_type,
    best_score, priority, type_score
def best_type(type_scores: dict[str, TypeScore]) -> TypeScore
def rank_accounts(accounts, scores, *, top_n: int, min_value: float,
                  excluded: set[str] = frozenset()) -> dict[str, list[RankedRow]]

# src/enrichment.py
def explain(row: RankedRow, account: Account) -> str

# src/digest.py
def render_digest(owner_id: str, rows: list[RankedRow], accounts: dict[str, Account]) -> str
def write_digests(ranked: dict[str, list[RankedRow]], accounts: list[Account], out_dir: Path) -> list[Path]

# src/feedback.py
def connect(db_path: Path | str) -> sqlite3.Connection
def init_db(conn: sqlite3.Connection) -> None
def record_feedback(conn, account_id: str, owner_id: str, action: str,
                    note: str = "", created_at: datetime | None = None) -> None
def excluded_accounts(conn: sqlite3.Connection) -> set[str]

# src/cli.py
def run_digest(data_dir: Path, config_path: Path, db_path: Path, out_dir: Path,
               top_n: int | None = None) -> list[Path]
def main(argv: list[str] | None = None) -> int
```

## Tests

| File | Covers |
|---|---|
| `tests/test_end_to_end.py` | same seed gives identical CSVs, scores and digests; at most one row per account and ≤ N rows per digest; CLI feedback removes the account from the next run |
| `tests/test_gates.py` | gate false, `0` or missing → exactly 0, for each gate in the test config and in the example config |
| `tests/test_ranking.py` | priority formula, fewer than 3 types, tie-break by account_id regardless of input order, top-N per owner, dedup, MIN_VALUE, zero-score accounts can fill slots |
| `tests/test_feedback.py` | both actions exclude, exclusion applies across owners, persists across connections, invalid action rejected |
| `tests/test_weight_normalization.py` | weights sum to 1 per type, ratios within a type preserved, disabled/negative/all-zero weights, flag off, every type tops out at 1.0 when all its signals are at 1.0 |
| `tests/test_normalization.py` | money cap on/off, zero values, missing signals, renewal cap (including days ≤ 0), seat_utilization with 0 seats and the 100% cap, disabled rules |

## Non-goals

No real data, warehouse connectors, chat or workflow integrations, ML,
auto-tuning or churn modelling.

## License

PLACEHOLDER. See `LICENSE`.
