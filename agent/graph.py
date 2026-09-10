"""
LangGraph skeleton for the Kovanica DevTeam agent.

Design rules baked into this file (do not weaken without a reason):
  1. `role` comes from the auth layer (main.py), never from the LLM or the
     user's message. A user can't talk their way into `dev` tools.
  2. run_cargo_command only ever executes inside the ephemeral sandbox
     container, never on the host, and only against the whitelisted verbs.
  3. Anything that would mutate the real repo (git_diff_suggest -> apply)
     is proposed, never applied, and requires a human confirmation via the
     /confirm endpoint. git_diff_suggest stages the proposal into the SQLite
     patchstore; on approval, main.py -> apply.py turns it into a throwaway
     git branch + draft PR (never touching the main checkout directly).
"""

import os
import re
import time
from typing import Literal, Optional, TypedDict, Annotated

import requests
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from rag import search_codebase as _rag_search_codebase
from checkpoint import get as _get_checkpoint
from sandbox_client import run_cargo as _sidecar_run_cargo
import patchstore as _patchstore

try:  # langgraph.config via contextvar; absent in some old runtimes
    from langgraph.config import get_config as _get_config
except Exception:  # pragma: no cover - defensive fallback
    _get_config = None


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or default).strip()


def _resolve_llm() -> ChatOpenAI:
    """Pick the OpenAI-compatible endpoint.

    Precedence:
      1. LLM_BASE_URL (+ LLM_API_KEY / XAI_API_KEY / OPENAI_API_KEY)
      2. VLLM_BASE_URL (compose: vLLM on GPU, Ollama on CPU)
    """
    explicit_base = _env("LLM_BASE_URL")
    vllm_base = _env("VLLM_BASE_URL", "http://vllm:8000/v1")
    key = _env("LLM_API_KEY") or _env("XAI_API_KEY") or _env("OPENAI_API_KEY") or "not-needed"
    if explicit_base:
        base = explicit_base
        default_model = "grok-4" if "x.ai" in explicit_base else "qwen2.5-coder:3b"
    else:
        base = vllm_base
        default_model = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
        if ":11434" in vllm_base or "ollama" in vllm_base.lower():
            default_model = "qwen2.5-coder:3b"
    model = _env("AGENT_MODEL") or default_model
    return ChatOpenAI(
        base_url=base,
        api_key=key,
        model=model,
        temperature=0.1,
        timeout=180,
        max_retries=1,
    )


QDRANT_URL = _env("QDRANT_URL", "http://qdrant:6333")
SANDBOX_IMAGE = _env("SANDBOX_IMAGE", "kovanica-sandbox:latest")
REPOS_PATH = _env("REPOS_PATH", "/repos/kovanica-protocol")

ALLOWED_CARGO_COMMANDS = {"check", "test", "clippy", "build"}
CARGO_TIMEOUT_SECONDS = 180


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    role: Literal["dev", "user"]
    pending_confirmation: Optional[dict]  # set when a diff is proposed


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_codebase(query: str) -> str:
    """Semantic + keyword search over the indexed Kovanica codebase and docs.
    Returns matching chunks with file path + line range so the agent can cite them.
    """
    return _rag_search_codebase(query)


@tool
def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Read a slice of a file from the read-only repo mount. Path is relative
    to the repo root, e.g. 'crates/kovanica-dag/src/ghostdag.rs'.
    """
    full_path = os.path.join(REPOS_PATH, path.lstrip("/"))
    if not os.path.abspath(full_path).startswith(os.path.abspath(REPOS_PATH)):
        return "ERROR: path escapes repo root"
    if not os.path.isfile(full_path):
        return f"ERROR: file not found: {path}"
    with open(full_path, "r", errors="replace") as f:
        lines = f.readlines()
    end_line = end_line or len(lines)
    return "".join(lines[start_line - 1:end_line])


@tool
def run_cargo_command(command: str, args: list[str] = []) -> str:
    """Run a whitelisted cargo command (check, test, clippy, build) against
    the repo, inside an ephemeral, network-disabled sandbox container.
    Delegates to the sandbox-runner sidecar (the only service that touches the
    Docker socket) so agent-api never holds Docker privileges itself.
    """
    if command not in ALLOWED_CARGO_COMMANDS:
        return f"REJECTED: '{command}' is not whitelisted ({sorted(ALLOWED_CARGO_COMMANDS)})"
    return _sidecar_run_cargo(command, list(args), repo_path=REPOS_PATH)


@tool
def git_diff_suggest(path: str, explanation: str, patch: str) -> str:
    """Propose a patch to a file. This NEVER writes to the real repo — it
    only stages a proposal that a human must approve via POST /confirm.
    On approval, apply.py turns the stored proposals into a throwaway git
    branch + draft PR.
    """
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:  # pragma: no cover - defensive
            session_id = ""
    if not session_id:
        session_id = os.environ.get("AGENT_SESSION_ID", "default")

    stored = False
    try:
        _patchstore.add_proposal(session_id, path, explanation, patch)
        stored = True
    except Exception as exc:  # pragma: no cover - a store failure must not break the gate
        stored = False

    note = (
        "PROPOSED (not applied). This diff is staged for human review and will "
        f"be applied to a throwaway branch + draft PR on /confirm.\n"
        f"File: {path}\nWhy: {explanation}\n---\n{patch}"
        + ("\n[staged=true]" if stored else "\n[staged=false: store write failed]")
    )
    return note


@tool
def query_node_api(endpoint: str) -> str:
    """Read-only GET against the local/testnet Kovanica node RPC, e.g. '/api/head'."""
    node_url = os.environ.get("KOVANICA_NODE_URL", "https://explorer.kovanica.online")

    _BLOCKED = {"mine", "faucet", "submit", "operator"}
    _ALLOWED = {
        "/api/head", "/api/state", "/api/blocks", "/api/bootstrap",
        "/api/history", "/api/utxos", "/api/origins", "/metrics",
        "/api/fee_estimate",
    }

    normalised = endpoint.strip()
    if any(tok in normalised.lower() for tok in _BLOCKED):
        return (
            f"REJECTED: endpoint '{normalised}' contains a blocked keyword "
            f"({_BLOCKED}). Only read-only endpoints are allowed."
        )
    if normalised not in _ALLOWED:
        return (
            f"REJECTED: endpoint '{normalised}' is not in the allowlist. "
            f"Allowed: {sorted(_ALLOWED)}"
        )

    url = f"{node_url.rstrip('/')}{normalised}"
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        body = resp.text[:4000]
        return body
    except requests.Timeout:
        return f"ERROR: request to {url} timed out after 8s"
    except requests.ConnectionError:
        return f"ERROR: could not connect to {url}"
    except requests.HTTPError:
        return f"ERROR: HTTP {resp.status_code} from {url}: {resp.text[:1000]}"
    except Exception as exc:
        return f"ERROR: {exc}"


@tool
def explain_concept(term: str) -> str:
    """Explain a GHOSTDAG/PHANTOM/consensus term using the project's own
    vocabulary (see SYSTEM_PROMPT.md glossary), grounded in the indexed docs.
    """
    results = search_codebase.invoke({"query": f"definition and usage of {term}"})
    preamble = (
        f"Below are excerpts from the Kovanica codebase that explain or "
        f"reference **{term}**:\n\n"
    )
    return preamble + results


DEV_TOOLS = [search_codebase, read_file, run_cargo_command, git_diff_suggest,
             query_node_api, explain_concept]
USER_TOOLS = [search_codebase, query_node_api, explain_concept]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

llm = _resolve_llm()

_prompt_path = os.path.join(os.path.dirname(__file__), "..", "SYSTEM_PROMPT.md")
if not os.path.isfile(_prompt_path):
    _prompt_path = "/SYSTEM_PROMPT.md"
with open(_prompt_path) as f:
    SYSTEM_PROMPT = f.read()

SYSTEM_PROMPT += (
    "\n\n## Answering\n"
    "Context from the codebase (and live node, when relevant) is injected for "
    "you. Answer in clear prose. Never emit tool-call JSON, never dump "
    "`{\"name\": ...}` as the reply, and never invent file paths.\n"
)


# ---------------------------------------------------------------------------
# Grounding (CPU 3B models cannot reliably bind_tools)
# ---------------------------------------------------------------------------

_LIVE_HINTS = (
    "head", "height", "tip", "testnet", "block count", "how many blocks",
    "network status", "current block",
)

_TOOL_JSON_RE = re.compile(
    r'\{\s*"name"\s*:\s*"(search_codebase|explain_concept|query_node_api|'
    r'read_file|run_cargo_command|git_diff_suggest)"',
    re.IGNORECASE,
)


def _msg_text(msg) -> str:
    c = getattr(msg, "content", "") or ""
    if isinstance(c, list):
        parts = []
        for p in c:
            if isinstance(p, dict):
                parts.append(str(p.get("text", "")))
            else:
                parts.append(str(p))
        return "".join(parts)
    return str(c)


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        kind = getattr(m, "type", None) or getattr(m, "role", None)
        if kind in ("human", "user") or isinstance(m, HumanMessage):
            return _msg_text(m)
    return _msg_text(messages[-1]) if messages else ""


def _grounding_context(question: str) -> str:
    """Always retrieve RAG (and live head when asked) so the 3B model
    does not have to emit a tool call to be useful."""
    chunks: list[str] = []
    try:
        found = _rag_search_codebase(question, k=4)
        if found:
            chunks.append(found[:4500])
    except Exception as exc:
        chunks.append(f"(code search unavailable: {exc.__class__.__name__})")
    q = (question or "").lower()
    if any(h in q for h in _LIVE_HINTS):
        try:
            live = query_node_api.invoke({"endpoint": "/api/head"})
            chunks.append("Live node /api/head:\n" + str(live)[:1500])
        except Exception:
            pass
    return "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def router(state: AgentState) -> AgentState:
    # `role` must already be set by main.py from the authenticated caller
    # (JWT/Keycloak claim), not inferred here from message content.
    return state


def agent_node(state: AgentState) -> AgentState:
    role = state.get("role") or "user"
    tools = DEV_TOOLS if role == "dev" else USER_TOOLS
    user_text = _last_user_text(state["messages"])
    grounding = _grounding_context(user_text) if user_text else ""

    sys = SYSTEM_PROMPT
    if grounding:
        sys += (
            "\n\n## Retrieved context (already fetched — do not emit tool-call JSON)\n"
            "Write a direct answer in prose. Cite file paths from this context "
            "when you use them.\n\n"
            + grounding
        )
    messages = [SystemMessage(content=sys), *state["messages"]]

    if role == "dev":
        response = llm.bind_tools(tools).invoke(messages)
    else:
        # qwen2.5-coder:3b via Ollama /v1 dumps fake tool JSON when bind_tools
        # is used; skip tools and answer from the retrieved context instead.
        response = llm.invoke(messages)

    text = _msg_text(response)
    if (
        role != "dev"
        and text
        and _TOOL_JSON_RE.search(text)
        and not getattr(response, "tool_calls", None)
    ):
        retry = messages + [
            AIMessage(content=text),
            HumanMessage(
                content=(
                    "Do not output JSON or tool calls. Answer the original "
                    "question in plain prose using the retrieved context."
                )
            ),
        ]
        response = llm.invoke(retry)

    return {"messages": [response]}


def tools_node(state: AgentState) -> AgentState:
    """Execute tool calls with the role-appropriate tool set.

    A single ToolNode(DEV_TOOLS) would let a user-role model that hallucinated
    a privileged tool name actually run it. Bind the node to USER_TOOLS when
    role != dev so cargo / read_file / git_diff_suggest are unreachable.
    """
    from langgraph.prebuilt import ToolNode
    tools = DEV_TOOLS if state.get("role") == "dev" else USER_TOOLS
    return ToolNode(tools).invoke(state)


def human_gate(state: AgentState) -> AgentState:
    """Reached only when the agent called git_diff_suggest. Graph execution
    stops here (see interrupt_before in build_graph) until main.py's
    /confirm endpoint resumes it with an approval or rejection.
    """
    last = state["messages"][-1]
    state["pending_confirmation"] = {
        "tool_call_id": getattr(last, "tool_call_id", None),
        "queued_at": time.time(),
    }
    return state


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return END
    if state.get("role") == "dev" and any(tc["name"] == "git_diff_suggest" for tc in tool_calls):
        return "human_gate"
    return "tools"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("human_gate", human_gate)

    graph.set_entry_point("router")
    graph.add_edge("router", "agent")
    graph.add_conditional_edges("agent", should_continue,
                                 {"tools": "tools", "human_gate": "human_gate", END: END})
    graph.add_edge("tools", "agent")
    graph.add_edge("human_gate", END)  # execution pauses; resumed externally

    checkpointer = _get_checkpoint()
    return graph.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])
