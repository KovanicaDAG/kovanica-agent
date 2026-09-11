"""
search-agent: dedicated semantic-search subagent service.

Owns: Qdrant connection, embedding, the two search collections
(kovanica_codebase, kovanica_skill_docs), and explain_concept.

The orchestrator (agent-api) calls this over HTTP instead of importing
rag.py directly. This makes search embeddable and independently deployable.

Endpoints
---------
GET  /healthz
GET  /readyz
POST /search       - codebase + skill-docs search in one call
POST /search/code  - codebase-only search
POST /search/docs  - skill-docs-only search
POST /explain      - explain_concept: grounded definition of a term
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Kovi Search Agent")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "kovanica_codebase")
QDRANT_SKILL_DOCS_COLLECTION = os.environ.get(
    "QDRANT_SKILL_DOCS_COLLECTION", "kovanica_skill_docs",
)
EMBED_MODULE = os.environ.get("EMBED_MODULE", "embed")


# ---------------------------------------------------------------------------
# Embedder (lazy, import-safe, shared with rag.py / indexer)
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
        return None


def _search_collection(query: str, collection: str, k: int, label: str) -> str:
    """Shared body: embed *query*, search *collection*, format hits."""
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


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    k_code: int = 5
    k_docs: int = 5


class ExplainRequest(BaseModel):
    term: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    return {"status": "ok", "name": "search-agent"}


@app.get("/readyz")
def readyz():
    client = _get_qdrant()
    embed = _get_embed_query()
    deps = {
        "qdrant": "ok" if client is not None else "unavailable",
        "embed": "ok" if embed is not None else "unavailable",
    }
    return {"status": "ok", "name": "search-agent", "deps": deps}


@app.post("/search/code", summary="Codebase-only semantic search")
def search_code(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return {"query": req.query, "results": _search_collection(
        req.query, QDRANT_COLLECTION, req.k_code, label="codebase",
    )}


@app.post("/search/docs", summary="Skill-docs semantic search")
def search_docs(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return {"query": req.query, "results": _search_collection(
        req.query, QDRANT_SKILL_DOCS_COLLECTION, req.k_docs, label="skill docs",
    )}


@app.post("/search", summary="Combined codebase + skill-docs search")
def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    return {
        "query": req.query,
        "code": _search_collection(
            req.query, QDRANT_COLLECTION, req.k_code, label="codebase",
        ),
        "docs": _search_collection(
            req.query, QDRANT_SKILL_DOCS_COLLECTION, req.k_docs, label="skill docs",
        ),
    }


@app.post("/explain", summary="Grounded explanation of a protocol term")
def explain(req: ExplainRequest):
    if not req.term.strip():
        raise HTTPException(status_code=400, detail="term is required")
    code_results = _search_collection(
        f"definition and usage of {req.term}", QDRANT_COLLECTION, 4, label="codebase",
    )
    doc_results = _search_collection(
        f"definition and usage of {req.term}", QDRANT_SKILL_DOCS_COLLECTION, 3,
        label="skill docs",
    )
    preamble = (
        f"Below are excerpts that explain or reference **{req.term}**, from the "
        f"Kovanica codebase and the protocol's skill/reference docs:\n\n"
    )
    return {"term": req.term, "explanation": preamble + code_results + "\n\n---\n\n" + doc_results}
