"""SQLite storage for run history. Schema in PRD §9."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB = Path("data/scratchers.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    games_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS game_snapshots (
    run_id                INTEGER NOT NULL REFERENCES runs(run_id),
    game_id               INTEGER NOT NULL,
    name                  TEXT,
    ticket_price          REAL,
    overall_odds          REAL,
    launch_date           TEXT,
    end_date              TEXT,
    redemption_date       TEXT,
    status                TEXT,
    tiers_json            TEXT,
    ev_per_ticket         REAL,
    ev_minus_price        REAL,
    est_tickets_remaining REAL,
    sanity_flag           TEXT,
    PRIMARY KEY (run_id, game_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_game ON game_snapshots(game_id);
"""


def _json_default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    raise TypeError(f"Not JSON serializable: {type(o).__name__}")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    with connect(db_path) as c:
        c.executescript(SCHEMA)


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at) VALUES (?)", (now_utc(),)
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, games_seen: int) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, games_seen = ? WHERE run_id = ?",
        (now_utc(), games_seen, run_id),
    )


def write_snapshot(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    game_id: int,
    name: str | None,
    ticket_price: Decimal | float | None,
    overall_odds: float | None,
    launch_date: date | None,
    end_date: date | None,
    redemption_date: date | None,
    status: str,
    tiers: list[Any] | None,
    ev_per_ticket: float | None,
    ev_minus_price: float | None,
    est_tickets_remaining: float | None,
    sanity_flag: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO game_snapshots
        (run_id, game_id, name, ticket_price, overall_odds,
         launch_date, end_date, redemption_date, status,
         tiers_json, ev_per_ticket, ev_minus_price,
         est_tickets_remaining, sanity_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            game_id,
            name,
            float(ticket_price) if ticket_price is not None else None,
            overall_odds,
            launch_date.isoformat() if launch_date else None,
            end_date.isoformat() if end_date else None,
            redemption_date.isoformat() if redemption_date else None,
            status,
            json.dumps(tiers, default=_json_default) if tiers is not None else None,
            ev_per_ticket,
            ev_minus_price,
            est_tickets_remaining,
            sanity_flag,
        ),
    )


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT run_id FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return int(row[0]) if row else None


def previous_run_id(conn: sqlite3.Connection) -> int | None:
    rows = conn.execute(
        "SELECT run_id FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY run_id DESC LIMIT 2"
    ).fetchall()
    return int(rows[1][0]) if len(rows) >= 2 else None


def snapshots_for_run(
    conn: sqlite3.Connection, run_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM game_snapshots WHERE run_id = ? ORDER BY game_id",
        (run_id,),
    ).fetchall()


def snapshot_for_game(
    conn: sqlite3.Connection, run_id: int, game_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM game_snapshots WHERE run_id = ? AND game_id = ?",
        (run_id, game_id),
    ).fetchone()
