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
from langgraph.prebuilt import ToolNode

from checkpoint import get as _get_checkpoint
from sandbox_client import run_cargo as _sidecar_run_cargo
import patchstore as _patchstore
import tools_ext as _te

try:  # langgraph.config via contextvar; absent in some old runtimes
    from langgraph.config import get_config as _get_config
except Exception:  # pragma: no cover - defensive fallback
    _get_config = None


def _search_agent_url() -> str:
    """Base URL of the search-agent subservice (HTTP, compose internal)."""
    return (
        (os.environ.get("SEARCH_AGENT_URL") or "").strip()
        or "http://search-agent:8082"
    )


def _search_agent_post(path: str, body: dict) -> dict:
    """POST to the search-agent subservice and return its JSON body.

    Falls back to a helpful error string when the subservice is unreachable
    (e.g. before it has started, or on a dev host without the compose stack).
    """
    url = (_search_agent_url() + path).rstrip("/")
    try:
        resp = requests.post(url, json=body, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {"error": f"search-agent not reachable at {url}"}
    except requests.Timeout:
        return {"error": f"search-agent timed out at {url}"}
    except requests.HTTPError as exc:
        return {"error": f"search-agent returned HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"error": str(exc)}

def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or default).strip()


def _resolve_llm() -> ChatOpenAI:
    """Pick the OpenAI-compatible LLM endpoint.

    The LLM is an external inference service speaking the OpenAI chat-completions
    protocol. Kovanica selects and talks to it; Kovanica itself provides the agent layer
    (tool use, graph, RAG, sandbox). Precedence:
      1. LLM_BASE_URL (+ LLM_API_KEY / XAI_API_KEY / OPENAI_API_KEY)
      2. VLLM_BASE_URL (compose: vLLM on GPU, Ollama on CPU)
    """
    explicit_base = _env("LLM_BASE_URL")
    vllm_base = _env("VLLM_BASE_URL", "http://vllm:8000/v1")
    key = _env("LLM_API_KEY") or _env("XAI_API_KEY") or _env("OPENAI_API_KEY") or "not-needed"
    if explicit_base:
        base = explicit_base
        default_model = "qwen2.5-coder:3b"
    else:
        base = vllm_base
        default_model = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
        if ":11434" in vllm_base or "ollama" in vllm_base.lower():
            default_model = "qwen2.5-coder:3b"
    model = _env("AGENT_MODEL") or default_model
    llm_timeout = int(_env("LLM_TIMEOUT") or 900)  # CPU Ollama is slow: prompt+gen can exceed 3 min
    return ChatOpenAI(
        base_url=base,
        api_key=key,
        model=model,
        temperature=0.1,
        timeout=llm_timeout,
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
    """Semantic + keyword search over the indexed Kovanica codebase.

    Delegates to the search-agent subservice over HTTP (compose internal)
    instead of importing rag.py directly, so search is an independently
    deployable service. Returns matching chunks with file path + line range.
    """
    body = _search_agent_post("/search/code", {"query": query, "k_code": 5, "k_docs": 5})
    if "error" in body:
        return f"(code search unavailable: {body['error']})"
    return body.get("results", body.get("code", str(body)))


@tool
def search_kovanica_docs(query: str) -> str:
    """Semantic search over the Kovanica Blockchain Developer skill's
    reference docs — RFC-001..006, tokenomics, GHOSTDAG notes, node ops,
    API shapes, mainnet checklist, FAQ, cheat-sheet.

    Delegates to the search-agent subservice over HTTP (compose internal).
    Results are tagged [skill_doc:...] — cite them as skill docs, never as
    repo file paths, and defer to the monorepo's own docs/ or code if the
    two disagree.
    """
    body = _search_agent_post("/search/docs", {"query": query, "k_code": 5, "k_docs": 5})
    if "error" in body:
        return f"(skill docs search unavailable: {body['error']})"
    return body.get("results", body.get("docs", str(body)))


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
        + ("[staged=true]" if stored else "[staged=false: store write failed]")
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
    """Explain a GHOSTDAG/PHANTOM/consensus/RFC/tokenomics term using the
    project's own vocabulary (see SYSTEM_PROMPT.md glossary), grounded in
    both the indexed code and the Kovanica skill's reference docs.
    """
    code_results = search_codebase.invoke({"query": f"definition and usage of {term}"})
    doc_results = search_kovanica_docs.invoke({"query": f"definition and usage of {term}"})
    preamble = (
        f"Below are excerpts that explain or reference **{term}**, from the "
        f"Kovanica codebase and the protocol's skill/reference docs:\n\n"
    )
    return preamble + code_results + "\n\n---\n\n" + doc_results


# ------------------------------------------------------------------
# Claude-code/Codex-style tools (NEW)
# ------------------------------------------------------------------

@tool
def glob_files(pattern: str, path: str = "") -> str:
    """Find files matching a glob pattern under the repo.

    Uses fnmatch against repo-relative paths. Supports ** recursive glob.
    Examples: glob_files("**/*.rs"), glob_files("crates/kovanica-dag/**")

    Parameters
    ----------
    pattern : str
        Glob pattern to match (e.g. "**/*.rs", "crates/**/main.rs").
    path : str
        Optional root directory for the search; defaults to the repo root.
    """
    return _te.glob_files(pattern, path or None)


@tool
def grep_files(pattern: str, path: str = "", case_sensitive: bool = True) -> str:
    """Search file contents for a literal or regex pattern.

    Uses rg (ripgrep) when available, falls back to grep. Only searches
    indexable file extensions (.rs, .md, .toml, .py, .sh, .yaml, .json, etc.).

    Parameters
    ----------
    pattern : str
        Pattern to search for (literal text or regex).
    path : str
        Optional directory to search under; defaults to the repo root.
    case_sensitive : bool
        Whether to respect case. Default True. Set False for -i behavior.
    """
    return _te.grep_files(pattern, path or None, case_sensitive)


@tool
def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    """Read a slice of a file from the read-only repo mount. Path is relative
    to the repo root, e.g. 'crates/kovanica-dag/src/ghostdag.rs'.

    This is the tool-binding entry point; the graph's ToolNode wires it.
    For CLI use, see the ``read_file`` function in kovi.
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
def edit_file(path: str, old_str: str, new_str: str,
              insert_line: Optional[int] = None, regex: bool = False,
              replace_all: bool = False) -> str:
    """Apply a targeted edit to a file. NEVER writes directly to the real repo
    without a human confirmation gate — this tool reports what it would do,
    and the apply path still requires /confirm for real mutations.

    For now this is a proposal tool: it writes to a throwaway staging area
    and returns a diff. Use git_diff_suggest for repo-persistent proposals.
    """
    repo_root = _te._repo_root()
    rel = _te._safe_edit_path(path)
    if rel is None:
        return f"ERROR: unsafe path: {path}"

    if not rel.is_file():
        if rel.parent.exists():
            return f"ERROR: file not found: {path}"
        # Preview mode: report what would be created
        return (f"[preview] Would create {path} with the following content "
                f"({len(new_str.splitlines())} lines):\n{new_str[:2000]}")

    lines = _te._read_lines(rel)
    text = "".join(lines)

    if old_str.strip():
        if regex:
            try:
                new_text = re.sub(old_str, new_str, text,
                                  count=0 if replace_all else 1)
            except re.error as exc:
                return f"ERROR: invalid regex: {exc}"
            if new_text == text:
                return f"ERROR: pattern not found in {path}"
            new_lines = new_text.splitlines(keepends=True)
            return (f"[preview] Would regex-replace in {path}: "
                    f"{len(lines)} → {len(new_lines)} lines.\n"
                    f"Old: {old_str[:200]}\nNew: {new_str[:200]}")
        else:
            if old_str not in text:
                return f"ERROR: old_str not found in {path}"
            new_text = text.replace(old_str, new_str,
                                    count=0 if replace_all else 1)
            new_lines = new_text.splitlines(keepends=True)
            return (f"[preview] Would replace in {path}: "
                    f"{len(lines)} → {len(new_lines)} lines.\n"
                    f"Old: {old_str[:200]}\nNew: {new_str[:200]}")
    elif insert_line is not None:
        if insert_line < 1:
            return f"ERROR: insert_line must be >= 1"
        if insert_line > len(lines):
            return f"ERROR: insert_line {insert_line} beyond EOF ({len(lines)} lines)"
        insert_lines = new_str.splitlines(keepends=True) or [new_str]
        return (f"[preview] Would insert {len(insert_lines)} line(s) after line "
                f"{insert_line} in {path}.\n{new_str[:500]}")
    else:
        return "ERROR: no operation specified (old_str or insert_line required)"


@tool
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file (repo-relative). Creates parent dirs.

    This is a proposal tool: it reports what would be written without
    touching the real repo. Use git_diff_suggest for repo-persistent proposals.
    """
    return _te.write_file(path, content, append=append)


@tool
def run_bash(command: str, workdir: str = "") -> str:
    """Run a whitelisted shell command and return stdout+stderr.

    Only whitelisted commands are allowed (ls, cat, head, tail, rg, grep,
    git status/log/diff/show, etc.). Network-modifying git commands
    (push, pull, fetch, clone) are blocked. Capped at 30s by default.

    Parameters
    ----------
    command : str
        Shell command to run (no shell metacharacters; plain argv).
    workdir : str
        Working directory; defaults to the repo root.
    """
    return _te.run_bash(command, workdir or None)


@tool
def task_add(description: str) -> str:
    """Add a todo task for the current session.

    Parameters
    ----------
    description : str
        Task description.
    """
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:
            session_id = os.environ.get("AGENT_SESSION_ID", "default")
    if not session_id:
        session_id = "default"
    task = _te.task_add(session_id, description)
    return f"Task added: [{task.id}] {task.content}"


@tool
def task_list() -> str:
    """List tasks for the current session."""
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:
            session_id = os.environ.get("AGENT_SESSION_ID", "default")
    if not session_id:
        session_id = "default"
    return _te.task_summary(session_id)


@tool
def task_done(task_id: str) -> str:
    """Mark a task done for the current session."""
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:
            session_id = os.environ.get("AGENT_SESSION_ID", "default")
    if not session_id:
        session_id = "default"
    return _te.task_done(session_id, task_id)


@tool
def task_remove(task_id: str) -> str:
    """Remove a task for the current session."""
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:
            session_id = os.environ.get("AGENT_SESSION_ID", "default")
    if not session_id:
        session_id = "default"
    return _te.task_remove(session_id, task_id)


@tool
def memory_recall(prefix: str = "") -> str:
    """Recall learned facts (user preferences, project conventions, etc.)."""
    return _te.memory_recall(prefix)


@tool
def memory_store(key: str, value: str) -> str:
    """Store a learned fact for future sessions."""
    session_id = ""
    if _get_config is not None:
        try:
            cfg = _get_config()
            session_id = str(cfg.get("configurable", {}).get("thread_id", ""))
        except Exception:
            session_id = os.environ.get("AGENT_SESSION_ID", "default")
    if not session_id:
        session_id = "default"
    return _te.memory_store(key, value, session_id)


DEV_TOOLS = [search_codebase, search_kovanica_docs, read_file, run_cargo_command,
             git_diff_suggest, query_node_api, explain_concept,
             glob_files, grep_files, edit_file, write_file, run_bash,
             task_add, task_list, task_done, task_remove,
             memory_recall, memory_store]
USER_TOOLS = [search_codebase, search_kovanica_docs, query_node_api, explain_concept,
              glob_files, grep_files, memory_recall]


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
    r'\{\s*"name"\s*:\s*"(search_codebase|search_kovanica_docs|explain_concept|'
    r'query_node_api|read_file|run_cargo_command|git_diff_suggest)"',
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
    try:
        found_docs = _rag_search_kovanica_docs(question, k=3)
        if found_docs:
            chunks.append(found_docs[:3500])
    except Exception as exc:
        chunks.append(f"(skill docs search unavailable: {exc.__class__.__name__})")
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
