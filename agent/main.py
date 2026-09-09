"""
FastAPI entrypoint. Routes:
  GET  /         - Kovi chat UI
  GET  /healthz  - liveness
  GET  /readyz   - dependency probe
  POST /chat     - send a message, get the agent's response (or a
                    "pending_confirmation" if it proposed a diff)
  POST /confirm  - approve or reject a pending diff, resumes the graph

Role is derived from auth, not from the request body. The `Authorization`
header is verified with real JWT auth (see auth.py): JWKS mode when
AUTH_JWKS_URL is set, dev-token mode otherwise. Only `dev` may confirm.

/confirm -> apply.gate: on approval, staged proposals (patchstore) are turned
into a throwaway git branch + draft PR by apply.py (fail-closed behind
AGENT_GIT_APPLY_ENABLED == "1"). On rejection or absence of proposals the
proposal store is cleared/resumed without touching any git repo.
"""

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import verify_token
from graph import build_graph
import patchstore as _patchstore
import apply as _apply

app = FastAPI(title="Kovi — Kovanica Engineering Agent")
agent_graph = build_graph()

STATIC_DIR = Path(__file__).resolve().parent / "static"
AUDIT_LOG = Path(os.environ.get("AGENT_AUDIT_LOG", "/data/audit.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

_CORS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "https://kovi.kovanica.online,https://kovanica.online,"
        "https://www.kovanica.online,https://explorer.kovanica.online",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_RATE_WINDOW_S = int(os.environ.get("AGENT_RATE_WINDOW_S", "60") or 60)
_RATE_LIMIT = int(os.environ.get("AGENT_RATE_LIMIT", "30") or 30)
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        return False
    q.append(now)
    return True


def audit(event: dict) -> None:
    event["ts"] = time.time()
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ConfirmRequest(BaseModel):
    session_id: str
    approve: bool


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="UI not packaged")
    return FileResponse(index_path)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.post("/chat")
def chat(req: ChatRequest, request: Request, authorization: str | None = Header(default=None)):
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests")
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > 8000:
        raise HTTPException(status_code=413, detail="message too long")

    role = verify_token(authorization)
    config = {"configurable": {"thread_id": req.session_id}}

    result = agent_graph.invoke(
        {"messages": [("user", message)], "role": role, "pending_confirmation": None},
        config=config,
    )

    audit({"session_id": req.session_id, "role": role, "event": "chat",
           "message": message[:500]})

    if result.get("pending_confirmation"):
        return {
            "status": "pending_confirmation",
            "detail": "Agent proposed a repo change. Review and POST /confirm.",
            "messages": [str(m.content) for m in result["messages"][-3:]],
        }

    return {"status": "ok", "reply": result["messages"][-1].content}


@app.post("/confirm")
def confirm(req: ConfirmRequest, request: Request, authorization: str | None = Header(default=None)):
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests")
    role = verify_token(authorization)
    if role != "dev":
        raise HTTPException(status_code=403, detail="Only dev role can confirm changes")

    config = {"configurable": {"thread_id": req.session_id}}

    audit({"session_id": req.session_id, "role": role, "event": "confirm",
           "approved": req.approve})

    if not req.approve:
        # Reject: drop the staged proposals and resume the graph to record the
        # human's decision without applying anything.
        _patchstore.clear(req.session_id)
        result = agent_graph.invoke(None, config=config)
        return {"status": "rejected", "detail": "Proposal discarded (not applied).",
                "reply": result["messages"][-1].content}

    # Approve: turn the staged proposals into a throwaway git branch + draft PR
    # via apply.py. This is the only path that touches a real git repo — dev
    # role only (checked above). Fail-closed: apply_and_open_pr returns a
    # dry_run/error unless AGENT_GIT_APPLY_ENABLED == "1".
    proposals = _patchstore.get_proposals(req.session_id)
    if not proposals:
        # No patchable proposal staged (e.g. the agent only answered a query);
        # still resume the graph past the gate so the session continues cleanly.
        result = agent_graph.invoke(None, config=config)
        return {"status": "approved", "reply": result["messages"][-1].content,
                "applied": []}

    apply_result = _apply.apply_and_open_pr(
        req.session_id, proposals, base=os.environ.get("AGENT_GIT_BASE", "main"),
        dry_run=(os.environ.get("AGENT_GIT_DRY_RUN", "1") == "1"),
    )

    if apply_result.status == "ok":
        _patchstore.mark_applied(req.session_id, [p.id for p in proposals])
    else:
        # Nothing was applied; keep the proposals so a corrected attempt (or
        # manual review) can still happen. Not clearing on error.
        pass

    audit({"session_id": req.session_id, "role": role, "event": "apply",
           "status": apply_result.status, "branch": apply_result.branch,
           "pr_url": apply_result.pr_url, "detail": apply_result.detail})

    # Resume the graph past the human gate so execution is not left dangling.
    try:
        result = agent_graph.invoke(None, config=config)
    except Exception as exc:  # pragma: no cover - resume is best-effort
        result = {"messages": []}

    return {
        "status": apply_result.status,
        "reply": result["messages"][-1].content if result.get("messages") else "",
        "applied_files": apply_result.applied_files,
        "branch": apply_result.branch,
        "pr_url": apply_result.pr_url,
        "detail": apply_result.detail,
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok", "name": "kovi"}


@app.get("/readyz")
def readyz():
    """Best-effort dependency probe. Liveness is /healthz; this is informational."""
    qdrant = os.environ.get("QDRANT_URL", "http://qdrant:6333")
    llm = os.environ.get("LLM_BASE_URL") or os.environ.get("VLLM_BASE_URL", "")
    deps = {"qdrant": "unknown", "llm": "unknown"}
    try:
        import requests
        r = requests.get(f"{qdrant.rstrip('/')}/readyz", timeout=2)
        deps["qdrant"] = "ok" if r.status_code < 500 else f"http {r.status_code}"
    except Exception as exc:
        deps["qdrant"] = f"error: {exc.__class__.__name__}"
    try:
        import requests
        if llm:
            r = requests.get(f"{llm.rstrip('/')}/models", timeout=2)
            deps["llm"] = "ok" if r.status_code < 500 else f"http {r.status_code}"
        else:
            deps["llm"] = "unset"
    except Exception as exc:
        deps["llm"] = f"error: {exc.__class__.__name__}"
    return {"status": "ok", "name": "kovi", "deps": deps}
