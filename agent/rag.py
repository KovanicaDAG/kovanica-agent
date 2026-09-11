"""
RAG search over the indexed Kovanica codebase via Qdrant.

Reuses the embedder the indexer sub-agent provides (``embed.embed_query``).
If that module is missing or the Qdrant collection hasn't been created yet,
every function degrades to a helpful message instead of a traceback.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "kovanica_codebase")
QDRANT_SKILL_DOCS_COLLECTION = os.environ.get(
    "QDRANT_SKILL_DOCS_COLLECTION", "kovanica_skill_docs",
)

# ---------------------------------------------------------------------------
# Embedder (lazy, import-safe)
# ---------------------------------------------------------------------------

_embed_query = None  # type: Optional[callable]

def _get_embed_query():
    """Return ``embed_query(text) -> list[float]``, importing once."""
    global _embed_query
    if _embed_query is not None:
        return _embed_query
    try:
        from embed import embed_query as _eq  # type: ignore[attr-defined]
        _embed_query = _eq
        return _embed_query
    except Exception as exc:
        log.warning("embed module unavailable (%s); search will return a stub", exc)
        return None


# ---------------------------------------------------------------------------
# Qdrant client (lazy)
# ---------------------------------------------------------------------------

_qdrant_client = None  # type: Optional[object]

def _get_qdrant():
    """Return a ``QdrantClient``, creating once."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    try:
        from qdrant_client import QdrantClient  # type: ignore[import-untyped]
        _qdrant_client = QdrantClient(url=QDRANT_URL)
        return _qdrant_client
    except Exception as exc:
        log.warning("Qdrant client unavailable (%s); search will return a stub", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _search_collection(query: str, collection: str, k: int, label: str) -> str:
    """Shared body: embed *query*, search *collection*, format hits.

    *label* is used only in the "not found" / "unavailable" error strings so
    callers get a message that names the right collection.
    """
    embed_fn = _get_embed_query()
    if embed_fn is None:
        return (
            "Search unavailable: the embed module could not be loaded. "
            "Make sure `embed.py` (and its dependencies) are installed."
        )

    client = _get_qdrant()
    if client is None:
        return (
            f"Search unavailable: could not connect to Qdrant at {QDRANT_URL}. "
            "Check that the Qdrant service is running."
        )

    try:
        vector = embed_fn(query)
    except Exception as exc:
        return f"Search error (embedding failed): {exc}"

    try:
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=k,
        )
    except Exception as exc:
        msg = str(exc)
        if "not found" in msg.lower() or "collection" in msg.lower():
            return (
                f"Collection '{collection}' not found in Qdrant. "
                f"Run the indexer first to populate the {label} vector store."
            )
        return f"Search error (Qdrant): {exc}"

    if not hits:
        return "No matching results found."

    lines: list[str] = []
    for hit in hits:
        payload = hit.payload or {}
        rel_path = payload.get("rel_path", payload.get("path", "unknown"))
        start = payload.get("start_line", payload.get("start", "?"))
        end = payload.get("end_line", payload.get("end", "?"))
        text = payload.get("text", payload.get("content", ""))
        source = payload.get("source", "code")
        score = hit.score
        lines.append(f"[{source}:{rel_path}:{start}-{end}] score={score:.2f}")
        lines.append(text)
    return "\n".join(lines)


def search_codebase(query: str, k: int = 5) -> str:
    """Semantic search over the ``kovanica_codebase`` Qdrant collection.

    Returns top-*k* hits formatted as::

        [source:rel_path:start_line-end_line] score=0.xx
        <text snippet>

    ``source`` is ``code`` for real repo files. Falls back to a helpful
    error string when dependencies or the collection are unavailable.
    """
    return _search_collection(query, QDRANT_COLLECTION, k, label="codebase")


def search_kovanica_docs(query: str, k: int = 5) -> str:
    """Semantic search over the ``kovanica_skill_docs`` Qdrant collection —
    the Kovanica Blockchain Developer skill's reference material (RFC-001
    through RFC-006, tokenomics, GHOSTDAG notes, node ops, API shapes,
    mainnet checklist, FAQ, cheat-sheet).

    These are protocol reference docs, not files in the kovanica-protocol
    repo — every hit is tagged ``source=skill_doc`` in its citation
    (``[skill_doc:tokenomics.md:12-34]``) so it is never mistaken for, or
    cited as, a real repo path. When the monorepo's own ``docs/`` disagrees
    with a skill doc, the monorepo wins (per the skill's own guidance) —
    say so if you notice a conflict rather than silently preferring one.

    Falls back to a helpful error string when dependencies or the
    collection are unavailable.
    """
    return _search_collection(
        query, QDRANT_SKILL_DOCS_COLLECTION, k, label="skill docs",
    )
