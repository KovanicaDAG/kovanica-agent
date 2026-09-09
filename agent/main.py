"""
FastAPI entrypoint. Two routes:
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
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from auth import verify_token
from graph import build_graph
import patchstore as _patchstore
import apply as _apply

app = FastAPI(title="Kovanica DevTeam Agent")
agent_graph = build_graph()

AUDIT_LOG = Path(os.environ.get("AGENT_AUDIT_LOG", "/data/audit.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


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


@app.post("/chat")
def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    role = verify_token(authorization)
    config = {"configurable": {"thread_id": req.session_id}}

    result = agent_graph.invoke(
        {"messages": [("user", req.message)], "role": role, "pending_confirmation": None},
        config=config,
    )

    audit({"session_id": req.session_id, "role": role, "event": "chat",
           "message": req.message})

    if result.get("pending_confirmation"):
        return {
            "status": "pending_confirmation",
            "detail": "Agent proposed a repo change. Review and POST /confirm.",
            "messages": [str(m.content) for m in result["messages"][-3:]],
        }

    return {"status": "ok", "reply": result["messages"][-1].content}


@app.post("/confirm")
def confirm(req: ConfirmRequest, authorization: str | None = Header(default=None)):
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
    return {"status": "ok"}
