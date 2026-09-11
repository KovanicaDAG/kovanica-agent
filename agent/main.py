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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Type

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import verify_token
from graph import build_graph
import patchstore as _patchstore

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


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
# Each registered action is a POST endpoint with:
#   path        - URL path (e.g. "/chat", "/confirm")
#   model       - Pydantic request body model
#   handler     - async def handler(req: Model, request: Request,
#                               authorization: str | None = Header(default=None))
#   summary     - optional OpenAPI summary
#   require_dev - if True, reject non-dev roles with 403 before the handler
#
# register_action() both registers the route on ``app`` and records metadata
# in _ACTION_REGISTRY so the set of live actions is introspectable (docs,
# tests, audit) without re-parsing FastAPI routes.

@dataclass
class ActionSpec:
    path: str
    model: Type[BaseModel]
    handler: Callable
    summary: str = ""
    require_dev: bool = False


_ACTION_REGISTRY: dict[str, ActionSpec] = {}


def register_action(
    path: str,
    model: Type[BaseModel],
    *,
    summary: str = "",
    require_dev: bool = False,
) -> Callable:
    """Decorator that registers a POST action on ``app`` and in the registry.

    Usage::

        @register_action("/chat", ChatRequest, summary="Send a message")
        async def chat(req: ChatRequest, request: Request,
                       authorization: str | None = Header(default=None)):
            ...
    """

    def decorator(handler: Callable) -> Callable:
        app.post(path, summary=summary or path)(handler)
        _ACTION_REGISTRY[path] = ActionSpec(
            path=path,
            model=model,
            handler=handler,
            summary=summary,
            require_dev=require_dev,
        )
        return handler

    return decorator


def list_actions() -> list[ActionSpec]:
    """Return the currently registered actions, in registration order."""
    return list(_ACTION_REGISTRY.values())


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ConfirmRequest(BaseModel):
    session_id: str
    approve: bool


# ---------------------------------------------------------------------------
# Static + health endpoints (direct decorators — stable, no body)
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="UI not packaged")
    return FileResponse(index_path)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "name": "kovi"}


@app.get("/readyz")
def readyz() -> dict:
    """Best-effort dependency probe. Liveness is /healthz; this is informational."""
    qdrant = os.environ.get("QDRANT_URL", "http://qdrant:6333")
    llm = os.environ.get("LLM_BASE_URL") or os.environ.get("VLLM_BASE_URL", "")
    deps: dict[str, str] = {"qdrant": "unknown", "llm": "unknown"}
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


# ---------------------------------------------------------------------------
# Registered POST actions
# ---------------------------------------------------------------------------

@register_action(
    "/chat",
    ChatRequest,
    summary="Send a message and get the agent's response",
)
async def chat(
    req: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
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

    audit(
        {"session_id": req.session_id, "role": role, "event": "chat", "message": message[:500]}
    )

    if result.get("pending_confirmation"):
        return {
            "status": "pending_confirmation",
            "detail": "Agent proposed a repo change. Review and POST /confirm.",
            "messages": [str(m.content) for m in result["messages"][-3:]],
        }

    last = result["messages"][-1]
    reply = getattr(last, "content", last)
    if isinstance(reply, list):
        reply = "".join(
            (p.get("text", "") if isinstance(p, dict) else str(p)) for p in reply
        )
    elif not isinstance(reply, str):
        reply = str(reply)
    return {"status": "ok", "reply": reply}


@register_action(
    "/confirm",
    ConfirmRequest,
    summary="Approve or reject a pending diff proposal",
    require_dev=True,
)
async def confirm(
    req: ConfirmRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests")
    role = verify_token(authorization)
    if role != "dev":
        raise HTTPException(status_code=403, detail="Only dev role can confirm changes")

    config = {"configurable": {"thread_id": req.session_id}}

    audit(
        {"session_id": req.session_id, "role": role, "event": "confirm", "approved": req.approve}
    )

    if not req.approve:
        # Reject: drop the staged proposals and resume the graph to record the
        # human's decision without applying anything.
        _patchstore.clear(req.session_id)
        return {
            "status": "rejected",
            "detail": "Proposal discarded (not applied).",
            "reply": "Proposal discarded.",
        }

    # ---------- no proposals: fast path ---------- #
    proposals = _patchstore.get_proposals(req.session_id)
    if not proposals:
        # No patchable proposal staged (e.g. the agent only answered a query);
        # nothing to apply — report approved with an empty applied list.
        return {
            "status": "approved",
            "reply": "No pending proposals to apply.",
            "applied": [],
        }

    # ---------- proposals: apply path ---------- #
    # Delegate to the apply-agent subservice over HTTP (compose internal).
    # This isolates git/gh/GPG mutations from the orchestrator process.
    apply_url = (
        (os.environ.get("APPLY_AGENT_URL") or "").strip()
        or "http://apply-agent:8083"
    ).rstrip("/")
    apply_body = {
        "session_id": req.session_id,
        "proposals": [
            {"path": p.path, "explanation": p.explanation, "patch": p.patch}
            for p in proposals
        ],
        "base": os.environ.get("AGENT_GIT_BASE", "main"),
    }
    try:
        apply_resp = requests.post(
            f"{apply_url}/apply", json=apply_body,
            timeout=int(os.environ.get("APPLY_AGENT_TIMEOUT_S", "180") or 180),
        )
        apply_resp.raise_for_status()
        apply_result = apply_resp.json()
    except requests.ConnectionError:
        return {
            "status": "error",
            "reply": f"apply-agent not reachable at {apply_url}",
            "detail": f"apply-agent not reachable at {apply_url}",
        }
    except requests.Timeout:
        return {
            "status": "error",
            "reply": "apply-agent timed out",
            "detail": "apply-agent timed out",
        }
    except requests.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return {
            "status": "error",
            "reply": detail,
            "detail": detail,
        }
    except Exception as exc:
        return {
            "status": "error",
            "reply": str(exc),
            "detail": str(exc),
        }

    if apply_result.get("status") == "ok":
        _patchstore.mark_applied(req.session_id, [p.id for p in proposals])

    audit(
        {
            "session_id": req.session_id,
            "role": role,
            "event": "apply",
            "status": apply_result.status,
            "branch": apply_result.branch,
            "pr_url": apply_result.pr_url,
            "detail": apply_result.detail,
        }
    )

    return {
        "status": apply_result.status,
        "reply": apply_result.detail or "Proposal processed.",
        "applied_files": apply_result.applied_files,
        "branch": apply_result.branch,
        "pr_url": apply_result.pr_url,
        "detail": apply_result.detail,
    }
