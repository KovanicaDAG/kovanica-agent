"""
Persistent LangGraph checkpointer backed by SQLite.

Replaces the in-memory ``MemorySaver`` so conversation state survives
restarts.  Import-safe: if ``langgraph.checkpoint.sqlite`` isn't installed
the module still loads; ``get_checkpoint()`` raises at call-time.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.environ.get(
    "AGENT_DB",
    str(Path(__file__).resolve().parent.parent / "data" / "agent.sqlite3"),
)


def get_checkpoint(path: str | None = None) -> object:
    """Return a persistent ``SqliteSaver`` checkpointer.

    Parameters
    ----------
    path:
        Filesystem path for the SQLite database.  Defaults to
        ``$AGENT_DB`` or ``kovanica-agent/data/agent.sqlite3``.

    Raises
    ------
    ImportError
        If ``langgraph.checkpoint.sqlite`` is not installed.

    Notes
    -----
    ``SqliteSaver.from_conn_string`` is a ``@contextmanager`` generator
    (it *yields* a ``SqliteSaver``, it does not return one) — calling it
    directly hands back a context-manager object, not a usable saver, and
    every graph invocation would fail. We open the underlying sqlite3
    connection ourselves instead (mirroring what ``from_conn_string`` does
    internally: ``check_same_thread=False``, since FastAPI's sync routes
    run on a threadpool) and construct ``SqliteSaver`` directly, keeping
    the connection open for the life of the process.
    """
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-untyped]

    db_path = Path(path or DEFAULT_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    log.info("Checkpointer opened at %s", db_path)
    return saver


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_checkpointer: Optional[object] = None


def get() -> object:
    """Return (and cache) the module-level persistent checkpointer."""
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = get_checkpoint()
    return _checkpointer
