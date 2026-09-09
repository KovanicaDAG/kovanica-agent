"""SQLite-backed store for proposed code patches, keyed by session id.

Proposals are repo-relative file patches produced by the agent and applied
later by ``apply.py``. Persistent across restarts via the same SQLite DB
file as the checkpointer (``$AGENT_DB``, default ``/data/agent.sqlite3``).
Lazily initialised on first use to avoid import-time side effects.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DB: sqlite3.Connection | None = None
# FastAPI serves sync routes from a threadpool, so the shared connection
# needs check_same_thread=False plus a lock around every use — sqlite3
# connections are not safe for concurrent use from multiple threads
# without one, even when check_same_thread is disabled.
_DB_LOCK = threading.Lock()


def _default_path() -> Path:
    return Path(os.environ.get("AGENT_DB", "/data/agent.sqlite3"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_default_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_path() -> Path:
    """Return the path to the shared SQLite database file."""
    return _default_path()


@dataclass
class Proposal:
    session_id: str
    path: str
    explanation: str
    patch: str
    id: int = 0
    created_ts: str = ""
    applied: int = 0


def init_db(path: Path | None = None) -> None:
    """Open (or create) the DB and ensure the ``proposals`` table exists.

    Idempotent; safe to call repeatedly. Confirm the parent directory exists.

    Parameters
    ----------
    path:
        Filesystem path for the SQLite database. Defaults to ``db_path()``.
    """
    global _DB
    db = _default_path() if path is None else Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    _DB = sqlite3.connect(str(db), check_same_thread=False)
    _DB.row_factory = sqlite3.Row
    _DB.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            path TEXT NOT NULL,
            explanation TEXT,
            patch TEXT,
            created_ts TEXT,
            applied INTEGER DEFAULT 0
        )
        """
    )
    _DB.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_session_id ON proposals (session_id)"
    )
    _DB.commit()


def _ensure_db() -> sqlite3.Connection:
    global _DB
    if _DB is None:
        init_db()
    assert _DB is not None
    return _DB


def add_proposal(session_id: str, path: str, explanation: str, patch: str) -> int:
    """Insert a proposal for ``session_id`` and return the new row id."""
    with _DB_LOCK:
        conn = _ensure_db()
        cur = conn.execute(
            """
            INSERT INTO proposals (session_id, path, explanation, patch, created_ts, applied)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (session_id, path, explanation, patch, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_proposals(session_id: str) -> list[Proposal]:
    """Return un-applied proposals for ``session_id`` in insertion order."""
    with _DB_LOCK:
        conn = _ensure_db()
        rows = conn.execute(
            """
            SELECT id, session_id, path, explanation, patch, created_ts, applied
            FROM proposals
            WHERE session_id = ? AND applied = 0
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return [
        Proposal(
            session_id=row["session_id"],
            path=row["path"],
            explanation=row["explanation"] or "",
            patch=row["patch"] or "",
            id=row["id"],
            created_ts=row["created_ts"] or "",
            applied=row["applied"],
        )
        for row in rows
    ]


def mark_applied(session_id: str, ids: list[int]) -> None:
    """Mark the given proposal ids for ``session_id`` as applied."""
    if not ids:
        return
    with _DB_LOCK:
        conn = _ensure_db()
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE proposals SET applied = 1 WHERE session_id = ? AND id IN ({placeholders})",
            [session_id, *ids],
        )
        conn.commit()


def clear(session_id: str) -> None:
    """Delete all proposals for ``session_id``."""
    with _DB_LOCK:
        conn = _ensure_db()
        conn.execute("DELETE FROM proposals WHERE session_id = ?", (session_id,))
        conn.commit()
