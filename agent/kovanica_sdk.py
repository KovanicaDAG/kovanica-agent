"""
Kovanica SDK — typed client for the Kovanica agent API.

Consumes the orchestrator (agent-api) HTTP surface and the subagent
search/apply services directly when they are reachable.

Public surface
--------------
KovanicaClient(base_url, token=None, timeout=60)
  .chat(session_id, message)        -> ChatReply
  .confirm(session_id, approve)    -> ChatReply
  .healthz()                        -> dict
  .readyz()                         -> dict
  .search(query, k_code=5, k_docs=5)  -> SearchReply   (if search-agent reachable)
  .explain(term)                    -> ExplainReply     (if search-agent reachable)

Search/apply subagents are optional: when they are not reachable the SDK
returns an error reply instead of crashing, so product code can degrade
gracefully (e.g. show "search not available" in the UI).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

try:
    import requests
except Exception:  # pragma: no cover - defensive
    requests = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data shapes (mirror the orchestrator + subagent wire format)
# ---------------------------------------------------------------------------


@dataclass
class ChatReply:
    status: str
    reply: str = ""
    detail: str = ""
    messages: list[str] = None
    applied: list = None
    applied_files: list[str] = None
    branch: str = ""
    pr_url: str = ""
    error: str = ""

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.applied is None:
            self.applied = []
        if self.applied_files is None:
            self.applied_files = []

    @property
    def is_pending(self) -> bool:
        return self.status == "pending_confirmation"

    @property
    def is_ok(self) -> bool:
        return self.status in ("ok", "approved")

    @property
    def is_error(self) -> bool:
        return self.status in ("error", "rejected") or bool(self.error)


@dataclass
class SearchReply:
    query: str = ""
    code: str = ""
    docs: str = ""
    error: str = ""

    @property
    def is_error(self) -> bool:
        return bool(self.error)


@dataclass
class ExplainReply:
    term: str = ""
    explanation: str = ""
    error: str = ""

    @property
    def is_error(self) -> bool:
        return bool(self.error)


@dataclass
class ApplyReply:
    status: str = ""
    branch: str = ""
    commit: str = ""
    pr_url: str = ""
    detail: str = ""
    applied_files: list[str] = None

    def __post_init__(self):
        if self.applied_files is None:
            self.applied_files = []

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_error(self) -> bool:
        return self.status in ("error",)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class KovanicaClient:
    """Typed, token-aware client for a Kovanica agent instance and its subagents.

    Parameters
    ----------
    base_url:
        Base URL of the orchestrator, e.g. ``https://kovanica.kovanica.online``
        or ``http://localhost:13080``. A trailing slash is stripped.
    token:
        Bearer token for ``Authorization``. Optional — omit for unauthenticated
        (user-role) requests against a dev-token instance.
    timeout:
        Per-request timeout in seconds. Default 60.
    search_agent_url:
        Optional base URL of the search-agent subservice. When provided (and
        reachable) ``search(...)`` and ``explain(...)`` delegate to it directly
        instead of going through the orchestrator. Defaults to None (disabled).
    apply_agent_url:
        Optional base URL of the apply-agent subservice. When provided the SDK
        can call ``apply(...)`` directly for advanced workflows. Defaults to
        None (disabled) — most product code uses ``confirm()`` on the
        orchestrator instead.
    """

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = 60,
        search_agent_url: Optional[str] = None,
        apply_agent_url: Optional[str] = None,
    ):
        if requests is None:
            raise RuntimeError(
                "The Kovanica SDK requires the 'requests' package. "
                "Install it with: pip install requests"
            )
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._search_url = (
            (search_agent_url or "").rstrip("/") or None
        )
        self._apply_url = (
            (apply_agent_url or "").rstrip("/") or None
        )

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _get(self, path: str) -> dict:
        r = requests.get(
            f"{self._base}{path}",
            headers=self._headers(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(
            f"{self._base}{path}",
            headers=self._headers(),
            json=body,
            timeout=self._timeout,
        )
        if r.status_code in (400, 401, 403, 404, 409, 413, 429, 500):
            try:
                return r.json()
            except Exception:
                return {"status": "error", "error": r.text[:500]}
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Core orchestrator endpoints
    # ------------------------------------------------------------------

    def chat(self, session_id: str, message: str) -> ChatReply:
        """Send a message and get the agent's response.

        When ``status == "pending_confirmation"`` the agent proposed a repo
        change; call ``confirm`` to approve/reject.
        """
        body = self._post("/chat", {"session_id": session_id, "message": message})
        return ChatReply(
            status=body.get("status", "error"),
            reply=body.get("reply", ""),
            detail=body.get("detail", ""),
            messages=body.get("messages", []),
        )

    def confirm(self, session_id: str, approve: bool) -> ChatReply:
        """Approve or reject a pending diff proposal (dev role only)."""
        body = self._post("/confirm", {"session_id": session_id, "approve": approve})
        return ChatReply(
            status=body.get("status", "error"),
            reply=body.get("reply", ""),
            detail=body.get("detail", ""),
            applied=body.get("applied", []),
            applied_files=body.get("applied_files", []),
            branch=body.get("branch", ""),
            pr_url=body.get("pr_url", ""),
        )

    def healthz(self) -> dict:
        """Liveness check on the orchestrator."""
        return self._get("/healthz")

    def readyz(self) -> dict:
        """Dependency probe on the orchestrator."""
        return self._get("/readyz")

    # ------------------------------------------------------------------
    # Optional search-agent endpoints (direct, low-latency RAG)
    # ------------------------------------------------------------------

    def search(self, query: str, k_code: int = 5, k_docs: int = 5) -> SearchReply:
        """Combined codebase + skill-docs semantic search.

        Requires ``search_agent_url`` to be configured at init time (or the
        SEARCH_AGENT_URL env var to be visible to the process). When the
        search-agent is not reachable the reply carries an ``error`` field.
        """
        if not self._search_url:
            return SearchReply(
                query=query,
                error="search not configured: pass search_agent_url to KovanicaClient",
            )
        try:
            r = requests.post(
                f"{self._search_url}/search",
                json={"query": query, "k_code": k_code, "k_docs": k_docs},
                timeout=self._timeout,
                headers=self._headers(),
            )
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                return SearchReply(query=query, error=body["error"])
            return SearchReply(
                query=body.get("query", query),
                code=body.get("code", ""),
                docs=body.get("docs", ""),
            )
        except requests.ConnectionError:
            return SearchReply(
                query=query,
                error=f"search-agent not reachable at {self._search_url}",
            )
        except requests.Timeout:
            return SearchReply(query=query, error="search-agent timed out")
        except Exception as exc:
            return SearchReply(query=query, error=str(exc))

    def explain(self, term: str) -> ExplainReply:
        """Grounded explanation of a protocol term (via search-agent)."""
        if not self._search_url:
            return ExplainReply(
                term=term,
                error="explain not configured: pass search_agent_url to KovanicaClient",
            )
        try:
            r = requests.post(
                f"{self._search_url}/explain",
                json={"term": term},
                timeout=self._timeout,
                headers=self._headers(),
            )
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                return ExplainReply(term=term, error=body["error"])
            return ExplainReply(
                term=body.get("term", term),
                explanation=body.get("explanation", ""),
            )
        except requests.ConnectionError:
            return ExplainReply(
                term=term,
                error=f"search-agent not reachable at {self._search_url}",
            )
        except requests.Timeout:
            return ExplainReply(term=term, error="search-agent timed out")
        except Exception as exc:
            return ExplainReply(term=term, error=str(exc))

    # ------------------------------------------------------------------
    # Optional apply-agent endpoint (direct, for advanced workflows)
    # ------------------------------------------------------------------

    def apply(self, session_id: str, proposals: list[dict], base: str = "main") -> ApplyReply:
        """Validate and apply proposals via the apply-agent subservice.

        Each proposal is a dict with ``path``, ``explanation``, ``patch``.
        The apply-agent is fail-closed: unless AGENT_GIT_APPLY_ENABLED=1 it
        only validates and reports (dry_run).

        Most product code should use ``confirm()`` on the orchestrator instead;
        this is available for tooling that wants to drive the apply path
        directly (e.g. a CLI that stages multiple proposals before confirming).
        """
        if not self._apply_url:
            return ApplyReply(
                status="error",
                detail="apply not configured: pass apply_agent_url to KovanicaClient",
            )
        body = {
            "session_id": session_id,
            "proposals": proposals,
            "base": base,
        }
        try:
            r = requests.post(
                f"{self._apply_url}/apply",
                json=body,
                timeout=self._timeout,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
            return ApplyReply(
                status=data.get("status", "error"),
                branch=data.get("branch", ""),
                commit=data.get("commit", ""),
                pr_url=data.get("pr_url", ""),
                detail=data.get("detail", ""),
                applied_files=data.get("applied_files", []),
            )
        except requests.ConnectionError:
            return ApplyReply(
                status="error",
                detail=f"apply-agent not reachable at {self._apply_url}",
            )
        except requests.Timeout:
            return ApplyReply(status="error", detail="apply-agent timed out")
        except Exception as exc:
            return ApplyReply(status="error", detail=str(exc))
