#!/usr/bin/env python3
"""
Kovanica REPL — interactive terminal conversation with multi-turn context.

Mirrors Claude Code / Codex REPL behaviour:
- Multi-turn conversation with persistent history in the session
- ``!``-prefixed inline commands: ``!ls``, ``!grep foo``, ``!read path 10 20``,
  ``!cargo test``, ``!bash echo hi``, ``!task add x``, ``!session list``,
  ``!memory recall``, ``!help``, ``!clear``, ``!quit``
- ``--json``: machine-readable output (tool results as JSON objects)
- ``--verbose``: detailed tool-call traces printed to stderr
- Auto-memory: user preferences/conventions learned from chat automatically
- Vault integration: session transcripts written to vault/Chats/ at end
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
AGENT_DIR = _HERE.parent  # /root/kovanica-agent (repl.py lives in agent/)
PROTOCOL_REPO = Path("/root/kovanica-protocol")

REPOS_PATH = os.environ.get("REPOS_PATH", "/repos/kovanica-protocol")
if not Path(REPOS_PATH).exists():
    REPOS_PATH = str(PROTOCOL_REPO)
if not Path(REPOS_PATH).exists():
    print(f"ERROR: protocol repo not found at {REPOS_PATH} or {PROTOCOL_REPO}", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(REPOS_PATH)

VAULT_ROOT = Path(os.environ.get("KOVANICA_VAULT_PATH", str(_HERE / "vault"))).resolve()
VAULT_CHATS = VAULT_ROOT / "Chats"
VAULT_MEMORY = VAULT_ROOT / "Memory"

# ---------------------------------------------------------------------------
# LLM resolution (mirrors kovi:resolve_llm)
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or default).strip()

def resolve_llm():
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
    return base, key, model

# ---------------------------------------------------------------------------
# System prompt (loaded from SYSTEM_PROMPT.md)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PATH = Path(AGENT_DIR) / "SYSTEM_PROMPT.md"
if not _SYSTEM_PROMPT_PATH.exists():
    _SYSTEM_PROMPT_PATH = Path("/SYSTEM_PROMPT.md")

with open(_SYSTEM_PROMPT_PATH) as f:
    SYSTEM_PROMPT = f.read()

SYSTEM_PROMPT += (
    "\n\n## Answering\n"
    "Context from the codebase (and live node, when relevant) is injected for "
    "you. Answer in clear prose. Never emit tool-call JSON, never dump "
    "`{\"name\": ...}` as the reply, and never invent file paths.\n"
    f"\n\n## Repo root\n"
    f"The protocol repository is at {REPO_ROOT} (REPOS_PATH={REPOS_PATH}). "
    "All file paths you cite must be relative to this root, e.g. "
    "`crates/kovanica-dag/src/ghostdag.rs`. If you cannot find a real path via "
    "search, say so rather than inventing one.\n"
)

# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

_LIVE_HINTS = (
    "head", "height", "tip", "testnet", "block count", "how many blocks",
    "network status", "current block",
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

def _last_user_text(messages):
    for m in reversed(messages or []):
        kind = getattr(m, "type", None) or getattr(m, "role", None)
        if kind in ("human", "user") or isinstance(m, HumanMessage):
            return _msg_text(m)
    return _msg_text(messages[-1]) if messages else ""

# ---------------------------------------------------------------------------
# Tool imports (same as kovi main)
# ---------------------------------------------------------------------------

import requests
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

try:
    sys.path.insert(0, str(_HERE / "agent"))
    import tools_ext as _te
except ImportError:
    _te = None

try:
    sys.path.insert(0, str(_HERE / "agent"))
    from sandbox_client import run_cargo as _sidecar_run_cargo
except ImportError:
    _sidecar_run_cargo = None

# ---------------------------------------------------------------------------
# New module imports (hooks, permission, subagents, mcp, plugins, github)
# ---------------------------------------------------------------------------

try:
    from agent import hooks as _hooks
except ImportError:
    _hooks = None

try:
    from agent import permission as _perm
except ImportError:
    _perm = None

try:
    from agent import subagents as _sub
except ImportError:
    _sub = None

try:
    from agent import mcp as _mcp
except ImportError:
    _mcp = None

try:
    from agent import plugins as _plugins
except ImportError:
    _plugins = None

try:
    from agent import github as _gh
except ImportError:
    _gh = None

# ---------------------------------------------------------------------------
# Tool call detection
# ---------------------------------------------------------------------------

_TOOL_JSON_RE = re.compile(
    r'\{\\\s*"name"\\s*:\\s*"(search_codebase|search_kovanica_docs|explain_concept|'
    r'query_node_api|read_file|run_cargo_command|git_diff_suggest|run_kovanica_cli)"',
    re.IGNORECASE,
)

def strip_fake_tool_json(text: str) -> str:
    text = re.sub(
        r'```json\s*\{[^}]*\"name\"\s*:\s*"(?:search_codebase|search_kovanica_docs|explain_concept|query_node_api|read_file|run_cargo_command|git_diff_suggest|run_kovanica_cli)"[^}]*\}\s*```',
        '', text, flags=re.DOTALL,
    )
    text = re.sub(
        r'\{"name"\s*:\s*"(?:search_codebase|search_kovanica_docs|explain_concept|query_node_api|read_file|run_cargo_command|git_diff_suggest|run_kovanica_cli)"[^}]*\}',
        '', text,
    )
    return text.strip()

# ---------------------------------------------------------------------------
# Inline command dispatcher (!ls, !grep, !read, !cargo, !bash, ...)
# ---------------------------------------------------------------------------

_INLINE_HELP = """\
Inline commands (prefix your message with !):
  !help              show this help
  !clear             clear conversation history (keep system prompt)
  !quit / !exit      leave REPL
  !glob <pattern>   find files by glob
  !grep <pattern>  search file contents
  !read <path> [start] [end]   read file slice
  !cargo <cmd> [args...]      run whitelisted cargo (check/test/clippy/build)
  !kovanica <args...>         run kovanica-cli binary
  !bash <cmd>      run whitelisted shell command
  !node <endpoint> query node RPC
  !task add|list|done|remove   todo management
  !session list|kill           session management
  !memory recall|store|forget  learned facts
  !diff <path> <why> <patch>   propose a patch (not applied)
  !explain <term>              explain a protocol term
  !search <query>              search codebase + docs
  !chat <message>              send to LLM (with full context)
Any other message (no ! prefix) is sent to the LLM as a chat turn."""

_INLINE_DISPATCH = {
    "help": "_inline_help",
    "clear": "_inline_clear",
    "quit": "_inline_quit",
    "exit": "_inline_quit",
}

def _inline_dispatch_cmd(cmd: str, args: list[str], verbose: bool, json_out: bool, session_id: str) -> dict[str, Any] | str:
    """Dispatch an inline command. Returns a dict (for --json) or a string."""
    if cmd in _INLINE_DISPATCH:
        handler_name = _INLINE_DISPATCH[cmd]
        handler = globals()[handler_name]
        return handler(args, verbose, json_out, session_id)

    # Permission gate for all tool dispatches
    gate = _dispatch_tool(cmd)
    if gate is not None:
        if json_out:
            return _tool_result_json(cmd, gate)
        return gate

    # Delegate to tools_ext for the real work
    if cmd == "glob":
        reply = _te.glob_files(args[0] if args else "", None, hidden=False) if _te else "ERROR: tools_ext not available"
    elif cmd == "grep":
        reply = _te.grep_files(args[0] if args else "", None, case_sensitive=True) if _te else "ERROR: tools_ext not available"
    elif cmd == "read":
        path = args[0] if args else ""
        start = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        end = int(args[2]) if len(args) > 2 and args[2].isdigit() else None
        reply = _te.read_file(path, start, end) if _te else f"ERROR: tools_ext not available"
    elif cmd == "cargo":
        if not args:
            reply = "ERROR: cargo subcommand required (check/test/clippy/build)"
        else:
            reply = run_cargo_command(args[0], args[1:])
    elif cmd == "kovanica":
        reply = run_kovanica_cli(args)
    elif cmd == "bash":
        reply = _te.run_bash(" ".join(args), None) if _te else "ERROR: tools_ext not available"
    elif cmd == "node":
        reply = query_node_api(args[0] if args else "/api/head")
    elif cmd == "task":
        reply = _dispatch_task(args, verbose, json_out, session_id)
    elif cmd == "session":
        reply = _dispatch_session(args, verbose, json_out)
    elif cmd == "memory":
        reply = _dispatch_memory(args, verbose, json_out, session_id)
    elif cmd == "diff":
        if len(args) < 3:
            reply = "ERROR: diff requires <path> <why> <patch>"
        else:
            reply = git_diff_suggest(args[0], args[1], args[2])
    elif cmd == "explain":
        reply = explain_concept(args[0] if args else "")
    elif cmd == "search":
        reply = search_codebase(args[0] if args else "")
    elif cmd == "chat":
        reply = chat(" ".join(args), session_id=session_id, role="dev", verbose=verbose, json_out=json_out)
    elif cmd == "hooks":
        reply = _dispatch_hooks(args, json_out)
    elif cmd == "subagent":
        reply = _dispatch_subagent(args, json_out, session_id)
    elif cmd == "mcp":
        reply = _dispatch_mcp(args, json_out)
    elif cmd == "gh":
        reply = _dispatch_gh(args, json_out)
    elif cmd == "permission":
        reply = _dispatch_permission(args, json_out)
    else:
        reply = f"ERROR: unknown inline command !{cmd}"

    if json_out:
        return _tool_result_json(cmd, reply)
    return reply

def _tool_result_json(cmd: str, reply: Any) -> dict[str, Any]:
    """Wrap a tool reply as a JSON object."""
    status = "ok" if isinstance(reply, str) and not reply.startswith("ERROR") and not reply.startswith("REJECTED") else "error"
    return {
        "tool": cmd,
        "status": status,
        "reply": reply,
    }

def _inline_help(args, verbose, json_out, session_id):
    if json_out:
        return {"tool": "help", "status": "ok", "reply": _INLINE_HELP}
    return _INLINE_HELP

def _inline_clear(args, verbose, json_out, session_id) -> str:
    """Clear conversation history."""
    return "Conversation history cleared (handled in REPL loop)."

def _inline_quit(args, verbose, json_out, session_id):
    sys.exit(0)

def _dispatch_task(args, verbose, json_out, session_id):
    if not args:
        return "ERROR: task subcommand required (add|list|done|remove)"
    sub = args[0]
    if sub == "add":
        t = _te.task_add(session_id, " ".join(args[1:])) if _te else None
        reply = f"Task added: [{t.id}] {t.content}" if t else "ERROR: tools_ext not available"
    elif sub == "list":
        reply = _te.task_summary(session_id) if _te else "ERROR: tools_ext not available"
    elif sub == "done":
        reply = _te.task_done(session_id, args[1] if len(args) > 1 else "") if _te else "ERROR: tools_ext not available"
    elif sub == "remove":
        reply = _te.task_remove(session_id, args[1] if len(args) > 1 else "") if _te else "ERROR: tools_ext not available"
    else:
        reply = f"ERROR: unknown task subcommand {sub}"
    if json_out:
        return _tool_result_json(f"task {sub}", reply)
    return reply

def _dispatch_session(args, verbose, json_out):
    if not args:
        return "ERROR: session subcommand required (list|kill)"
    sub = args[0]
    if sub == "list":
        reply = _te.session_list() if _te else "ERROR: tools_ext not available"
    elif sub == "kill":
        reply = _te.session_kill(args[1] if len(args) > 1 else "") if _te else "ERROR: tools_ext not available"
    else:
        reply = f"ERROR: unknown session subcommand {sub}"
    if json_out:
        return _tool_result_json(f"session {sub}", reply)
    return reply

def _dispatch_memory(args, verbose, json_out, session_id):
    if not args:
        reply = _te.memory_recall("") if _te else "ERROR: tools_ext not available"
    elif args[0] == "recall":
        reply = _te.memory_recall(args[1] if len(args) > 1 else "") if _te else "ERROR: tools_ext not available"
    elif args[0] == "store":
        if len(args) < 3:
            reply = "ERROR: memory store requires <key> <value>"
        else:
            reply = _te.memory_store(args[1], " ".join(args[2:]), session_id) if _te else "ERROR: tools_ext not available"
    elif args[0] == "forget":
        reply = _te.memory_forget(args[1] if len(args) > 1 else "") if _te else "ERROR: tools_ext not available"
    else:
        reply = f"ERROR: unknown memory subcommand {args[0]}"
    if json_out:
        return _tool_result_json(f"memory {args[0] if args else 'recall'}", reply)
    return reply


# ---------------------------------------------------------------------------
# Permission-gated tool dispatch (single gate for all tool use in chat path)
# ---------------------------------------------------------------------------

def _dispatch_tool(tool_name: str, tool_args: dict | None = None) -> str | None:
    """
    Permission gate for ALL tool use — both ! inline commands and chat-path tools.

    Calls _perm.can_run(tool_name) before dispatching. Returns a REJECTED string
    if denied, or None if allowed (caller proceeds with the actual dispatch).
    """
    if _perm and not _perm.can_run(tool_name):
        return f"REJECTED: {tool_name} not allowed in current permission mode ({_perm.get_mode()})"

    # Fire PreToolUse hooks if available
    if _hooks:
        _hooks._fire_pre_tool_use(tool_name, tool_args or {})

    return None  # allowed — caller dispatches


def _after_tool(tool_name: str, tool_args: dict, result: Any) -> None:
    """Fire PostToolUse hooks after a tool returns."""
    if _hooks:
        _hooks._fire_post_tool_use(tool_name, tool_args, result)

# ---------------------------------------------------------------------------
# Dispatch helpers for new modules (hooks, subagent, mcp, gh, permission)
# ---------------------------------------------------------------------------

def _dispatch_hooks(args: list[str], json_out: bool) -> str | dict:
    if not args:
        if _hooks:
            hooks = _hooks.list_hooks()
            if json_out:
                return {"tool": "hooks", "status": "ok", "reply": hooks}
            return "Registered hooks:\n" + "\n".join(f"  - {h['name']} (agent={h['agent'] or 'all'})" for h in hooks) or "(no hooks registered)"
        return "ERROR: hooks module not available"
    sub = args[0]
    if sub == "list":
        if _hooks:
            hooks = _hooks.list_hooks()
            if json_out:
                return {"tool": "hooks list", "status": "ok", "reply": hooks}
            return "Registered hooks:\n" + "\n".join(f"  - {h['name']} (agent={h['agent'] or 'all'})" for h in hooks) or "(no hooks registered)"
        return "ERROR: hooks module not available"
    if sub == "clear":
        if _hooks:
            cleared = _hooks.clear_hooks()
            if json_out:
                return {"tool": "hooks clear", "status": "ok", "reply": cleared}
            return f"Cleared {cleared['removed']} hooks"
        return "ERROR: hooks module not available"
    if sub == "add":
        if len(args) < 4:
            return "ERROR: hooks add requires <name> <agent|null> <trigger> <path>"
        name, agent, trigger, path = args[0], args[1] if args[1] != "null" else None, args[2], args[3]
        if _hooks:
            result = _hooks.add_hook(name, agent, trigger, path)
            if json_out:
                return {"tool": "hooks add", "status": "ok" if result.get("status") == "added" else "error", "reply": result}
            return f"Hook added: {name} (agent={agent or 'all'}, trigger={trigger}, path={path})" if result.get("status") == "added" else f"ERROR: {result.get('error', result)}"
        return "ERROR: hooks module not available"
    if sub == "remove":
        if len(args) < 2:
            return "ERROR: hooks remove requires <name> [agent]"
        name, agent = args[0], args[1] if len(args) > 1 and args[1] != "null" else None
        if _hooks:
            result = _hooks.remove_hook(name, agent)
            if json_out:
                return {"tool": "hooks remove", "status": "ok", "reply": result}
            return f"Removed {result['removed']} hook(s) named {name}"
        return "ERROR: hooks module not available"
    return f"ERROR: unknown hooks subcommand {sub}"

def _dispatch_subagent(args: list[str], json_out: bool, session_id: str) -> str | dict:
    if not args:
        if _sub:
            agents = _sub.list_subagents()
            if json_out:
                return {"tool": "subagent", "status": "ok", "reply": agents}
            return "Available subagents:\n" + "\n".join(f"  - {a['name']}: {a['description']}" for a in agents)
        return "ERROR: subagents module not available"
    subcmd = args[0]
    if subcmd == "list":
        if _sub:
            agents = _sub.list_subagents()
            if json_out:
                return {"tool": "subagent list", "status": "ok", "reply": agents}
            return "Available subagents:\n" + "\n".join(f"  - {a['name']}: {a['description']}" for a in agents)
        return "ERROR: subagents module not available"
    if subcmd == "running":
        if _sub:
            running = _sub.list_running_subagents(session_id)
            if json_out:
                return {"tool": "subagent running", "status": "ok", "reply": running}
            return "Running subagents:\n" + "\n".join(f"  - {r['id']}: {r['name']} ({r['status']}, {r['turns']} turns)" for r in running) or "(none running)"
        return "ERROR: subagents module not available"
    if subcmd == "spawn":
        if len(args) < 3:
            return "ERROR: subagent spawn requires <name> <task> [model|null] [permission_mode]"
        name = args[1] if len(args) > 1 else ""
        task = args[2] if len(args) > 2 else ""
        model = args[3] if len(args) > 3 and args[3] != "null" else None
        perm_mode = args[4] if len(args) > 4 else None
        if _sub:
            result = _sub.spawn_subagent(name, task, session_id, model, perm_mode)
            if json_out:
                return {"tool": "subagent spawn", "status": "ok" if result.get("id") else "error", "reply": result}
            if result.get("id"):
                return f"Spawned subagent {result['id']}: {name} — {task} (model={result['model'] or 'inherit'}, perm={result['permission_mode']})"
            return f"ERROR: {result.get('error', result)}"
        return "ERROR: subagents module not available"
    if subcmd == "status":
        if len(args) < 2:
            return "ERROR: subagent status requires <run_id>"
        run_id = args[1]
        if _sub:
            status = _sub.get_subagent(run_id)
            if json_out:
                return {"tool": "subagent status", "status": "ok" if status else "error", "reply": status or {}}
            return f"Subagent {run_id}: {status['status'] if status else 'not found'}" if status else f"ERROR: subagent {run_id} not found"
        return "ERROR: subagents module not available"
    if subcmd == "stop":
        if len(args) < 2:
            return "ERROR: subagent stop requires <run_id>"
        run_id = args[1]
        if _sub:
            result = _sub.stop_subagent(run_id)
            if json_out:
                return {"tool": "subagent stop", "status": "ok" if result.get("status") == "stopped" else "error", "reply": result}
            return f"Stopped subagent {run_id}" if result.get("status") == "stopped" else f"ERROR: {result.get('error', result)}"
        return "ERROR: subagents module not available"
    if subcmd == "return":
        if len(args) < 3:
            return "ERROR: subagent return requires <run_id> <result_json>"
        run_id = args[1]
        try:
            result_val = json.loads(" ".join(args[2:]))
        except Exception:
            return "ERROR: subagent return result must be valid JSON"
        if _sub:
            result = _sub.return_subagent_result(run_id, result_val)
            if json_out:
                return {"tool": "subagent return", "status": "ok" if result.get("status") == "returned" else "error", "reply": result}
            gated = result.get("result")
            return f"Subagent {run_id} returned (gated: {gated})" if result.get("status") == "returned" else f"ERROR: {result.get('error', result)}"
        return "ERROR: subagents module not available"
    return f"ERROR: unknown subagent subcommand {subcmd}"

def _dispatch_mcp(args: list[str], json_out: bool) -> str | dict:
    if not args:
        if _mcp:
            servers = _mcp.list_mcp_tools()
            if json_out:
                return {"tool": "mcp", "status": "ok", "reply": servers}
            lines = ["Registered MCP servers:"]
            for name, tools in servers.items():
                lines.append(f"  {name}: {len(tools)} tool(s)")
            return "\n".join(lines)
        return "ERROR: mcp module not available"
    subcmd = args[0]
    if subcmd == "list":
        if _mcp:
            servers = _mcp.list_mcp_tools()
            if json_out:
                return {"tool": "mcp list", "status": "ok", "reply": servers}
            lines = ["Registered MCP servers:"]
            for name, tools in servers.items():
                lines.append(f"  {name}: {len(tools)} tool(s)")
            return "\n".join(lines)
        return "ERROR: mcp module not available"
    if subcmd == "register":
        if len(args) < 4:
            return "ERROR: mcp register requires <name> <transport> <command|url>"
        name, transport = args[1], args[2]
        third = args[3] if len(args) > 3 else ""
        if transport == "http":
            result = _mcp.register_mcp_server(name, "http", url=third) if _mcp else None
        else:
            # stdio: parse command as space-separated list
            cmd = third.split() if third else []
            result = _mcp.register_mcp_server(name, "stdio", command=cmd) if _mcp else None
        if not _mcp:
            return "ERROR: mcp module not available"
        if result.get("error"):
            if json_out:
                return {"tool": "mcp register", "status": "error", "reply": result}
            return f"ERROR: {result['error']}"
        if json_out:
            return {"tool": "mcp register", "status": "ok", "reply": result}
        return f"Registered MCP server {name} (transport={transport})"
    if subcmd == "unregister":
        if len(args) < 2:
            return "ERROR: mcp unregister requires <name>"
        name = args[1]
        if _mcp:
            result = _mcp.unregister_mcp_server(name)
            if json_out:
                return {"tool": "mcp unregister", "status": "ok" if result.get("status") == "unregistered" else "error", "reply": result}
            return f"Unregistered MCP server {name}" if result.get("status") == "unregistered" else f"ERROR: {result.get('error', result)}"
        return "ERROR: mcp module not available"
    if subcmd == "call":
        if len(args) < 4:
            return "ERROR: mcp call requires <server> <tool> <json_args>"
        server, tool = args[1], args[2]
        try:
            args_dict = json.loads(" ".join(args[3:]))
        except Exception:
            return "ERROR: mcp call arguments must be valid JSON"
        if _mcp:
            result = _mcp.call_mcp_tool(server, tool, args_dict)
            if json_out:
                return {"tool": "mcp call", "status": "ok", "reply": result}
            return f"MCP call result: {json.dumps(result)}"
        return "ERROR: mcp module not available"
    return f"ERROR: unknown mcp subcommand {subcmd}"

def _dispatch_gh(args: list[str], json_out: bool) -> str | dict:
    if not args:
        if _gh:
            if json_out:
                return {"tool": "gh", "status": "ok", "reply": {"available": _gh._gh_available()}}
            return f"gh CLI available: {_gh._gh_available()}"
        return "ERROR: github module not available"
    subcmd = args[0]
    if subcmd == "list":
        if _gh:
            prs = _gh.gh_pr_list()
            if json_out:
                return {"tool": "gh list", "status": "ok", "reply": prs}
            if not prs:
                return "No open PRs"
            return "Open PRs:\n" + "\n".join(f"  #{p['number']}: {p['title']} ({p['url']})" for p in prs)
        return "ERROR: github module not available"
    if subcmd == "view":
        if len(args) < 2:
            return "ERROR: gh view requires <pr_number>"
        try:
            num = int(args[1])
        except ValueError:
            return "ERROR: gh view pr_number must be an integer"
        if _gh:
            result = _gh.gh_pr_view(num)
            if json_out:
                return {"tool": "gh view", "status": "ok" if "error" not in result else "error", "reply": result}
            if "error" in result:
                return f"ERROR: {result['error']}"
            return f"PR #{result.get('number')}: {result.get('title')} — {result.get('state')}"
        return "ERROR: github module not available"
    if subcmd == "review":
        if len(args) < 3:
            return "ERROR: gh review requires <pr_number> <comment>"
        try:
            num = int(args[1])
        except ValueError:
            return "ERROR: gh review pr_number must be an integer"
        comment = " ".join(args[2:])
        if _gh:
            result = _gh.gh_pr_review(num, [comment])
            if json_out:
                return {"tool": "gh review", "status": "ok" if result.get("status") == "ok" else "error", "reply": result}
            return f"Review posted on PR #{num}" if result.get("status") == "ok" else f"ERROR: {result.get('error', result)}"
        return "ERROR: github module not available"
    return f"ERROR: unknown gh subcommand {subcmd}"

def _dispatch_permission(args: list[str], json_out: bool) -> str | dict:
    if not args:
        if _perm:
            mode = _perm.get_mode()
            if json_out:
                return {"tool": "permission", "status": "ok", "reply": {"mode": mode}}
            return f"Current permission mode: {mode}"
        return "ERROR: permission module not available"
    subcmd = args[0]
    if subcmd == "get":
        if _perm:
            mode = _perm.get_mode()
            if json_out:
                return {"tool": "permission get", "status": "ok", "reply": {"mode": mode}}
            return f"Current permission mode: {mode}"
        return "ERROR: permission module not available"
    if subcmd == "set":
        if len(args) < 2:
            return "ERROR: permission set requires <mode>"
        mode = args[1]
        if _perm:
            valid = {"manual", "acceptEdits", "auto", "plan"}
            if mode not in valid:
                if json_out:
                    return {"tool": "permission set", "status": "error", "reply": {"error": f"invalid mode {mode!r}, must be one of {sorted(valid)}"}}
                return f"ERROR: invalid mode {mode!r}, must be one of {sorted(valid)}"
            _perm.set_mode(mode)
            if json_out:
                return {"tool": "permission set", "status": "ok", "reply": {"mode": mode}}
            return f"Permission mode set to {mode}"
        return "ERROR: permission module not available"
    if subcmd == "check":
        if len(args) < 2:
            return "ERROR: permission check requires <tool_name>"
        tool = args[1]
        if _perm:
            allowed, reason = _perm.check(tool)
            if json_out:
                return {"tool": "permission check", "status": "ok", "reply": {"tool": tool, "allowed": allowed, "reason": reason, "mode": _perm.get_mode()}}
            mark = "ALLOWED" if allowed else "BLOCKED"
            return f"{mark}: {tool} in {mode} mode — {reason}"
        return "ERROR: permission module not available"
    if subcmd == "can-run":
        if len(args) < 2:
            return "ERROR: permission can-run requires <tool_name>"
        tool = args[1]
        if _perm:
            ok = _perm.can_run(tool)
            if json_out:
                return {"tool": "permission can-run", "status": "ok", "reply": {"tool": tool, "can_run": ok, "mode": _perm.get_mode()}}
            return f"{'CAN' if ok else 'CANNOT'} run {tool} in {_perm.get_mode()} mode"
        return "ERROR: permission module not available"
    return f"ERROR: unknown permission subcommand {subcmd}"

# ---------------------------------------------------------------------------
# Conversation state
# ---------------------------------------------------------------------------

class Conversation:
    """Multi-turn conversation state for the REPL."""

    def __init__(self, session_id: str, role: str = "dev", verbose: bool = False, json_out: bool = False, model: str | None = None):
        self.session_id = session_id
        self.role = role
        self.verbose = verbose
        self.json_out = json_out
        self.model = model  # persisted model for this session
        self.messages: list[HumanMessage | AIMessage | SystemMessage] = []
        self._system_prompt = SYSTEM_PROMPT
        self._add_system()

    def _add_system(self):
        self.messages.insert(0, SystemMessage(content=self._system_prompt))

    def reset(self):
        """Clear conversation history, keep system prompt."""
        self.messages = []
        self._add_system()

    def add_user(self, text: str):
        self.messages.append(HumanMessage(content=text))

    def add_assistant(self, text: str):
        self.messages.append(AIMessage(content=text))

    def last_user_text(self) -> str:
        return _last_user_text(self.messages)

    def num_turns(self) -> int:
        """Count user+assistant pairs (excluding system)."""
        n = len(self.messages) - 1  # minus system
        return max(0, n // 2)

# ---------------------------------------------------------------------------
# Auto-memory: learn user preferences from chat
# ---------------------------------------------------------------------------

# Patterns that suggest a user preference or convention
_PREFERENCE_PATTERNS = [
    (re.compile(r'\b(I\s+prefer|I\s+like|my\s+preferred|we\s+prefer)\s+(.+)', re.IGNORECASE), "preference"),
    (re.compile(r'\b(always|never|must|should)\s+(.+)', re.IGNORECASE), "convention"),
    (re.compile(r'\b(use|stick\s+to|follow)\s+(.+?)(?:\.|$|\s+for|\s+when)', re.IGNORECASE), "preference"),
    (re.compile(r'\b(remember|note|keep\s+in\s+mind)\s+(.+)', re.IGNORECASE), "note"),
]

def _extract_preferences(text: str, session_id: str) -> list[tuple[str, str, str]]:
    """Extract (key, value, category) tuples from user text."""
    results = []
    seen_keys = set()
    for pattern, category in _PREFERENCE_PATTERNS:
        for m in pattern.finditer(text):
            full = m.group(0).strip()
            value = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else full
            key = hashlib.sha256(full.encode()).hexdigest()[:12]
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append((f"pref:{key}", value, category))
    return results

def _auto_memory_from_turn(user_text: str, session_id: str, verbose: bool):
    """Scan user text for preferences and store them automatically."""
    prefs = _extract_preferences(user_text, session_id)
    for key, value, category in prefs:
        if _te:
            _te.memory_store(key, value, session_id, source=f"auto-{category}")
            if verbose:
                print(f"[auto-memory] stored: {key} = {value} (category: {category})", file=sys.stderr)
        else:
            if verbose:
                print(f"[auto-memory] SKIP: tools_ext not available", file=sys.stderr)

# ---------------------------------------------------------------------------
# Vault integration
# ---------------------------------------------------------------------------

def _ensure_vault_dirs():
    VAULT_CHATS.mkdir(parents=True, exist_ok=True)
    VAULT_MEMORY.mkdir(parents=True, exist_ok=True)

def _write_session_to_vault(session_id: str, conversation: Conversation):
    """Write a session transcript to vault/Chats/<timestamp>-<session_id>.md."""
    _ensure_vault_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts}-{session_id}.md"
    path = VAULT_CHATS / filename
    lines = [
        "---\n",
        f"session: {session_id}\n",
        f"created: {ts}\n",
        f"turns: {conversation.num_turns()}\n",
        "---\n",
        "\n# Session {session_id}\n",
        "\n",
    ]
    for msg in conversation.messages[1:]:  # skip system
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        text = _msg_text(msg)
        lines.append(f"## {role}\n")
        lines.append(text)
        lines.append("\n")
    try:
        path.write_text("".join(lines), encoding="utf-8")
        print(f"[vault] session saved to {path}", file=sys.stderr)
    except Exception as exc:
        print(f"[vault] ERROR writing session: {exc}", file=sys.stderr)

def _vault_memory_recall(prefix: str = "") -> str:
    """Recall memory from vault/Memory/*.md notes (YAML frontmatter)."""
    _ensure_vault_dirs()
    results = []
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    for md_file in sorted(VAULT_MEMORY.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            m = pattern.match(text)
            if not m:
                continue
            fm_text = m.group(1)
            fm: dict[str, str] = {}
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            if prefix and not fm.get("key", "").startswith(prefix):
                continue
            results.append(f"  [{fm.get('source', 'vault')}] {fm.get('key', '?')} = {fm.get('value', '?')}  (learned {fm.get('learned_ts', '?')[:10] if fm.get('learned_ts') else ''})")
        except Exception:
            pass
    if not results:
        return "(no vault memory recalled)"
    return f"Recalled {len(results)} vault memory entry/ies:\n" + "\n".join(results)

def _vault_memory_store(key: str, value: str, session_id: str, source: str = "auto") -> str:
    """Store a memory as vault/Memory/<slug>.md with YAML frontmatter."""
    _ensure_vault_dirs()
    slug = re.sub(r"[^\w-]", "-", key)[:50]
    ts = datetime.now(timezone.utc).isoformat()
    path = VAULT_MEMORY / f"{slug}.md"
    frontmatter = f"""\
---
key: {key}
value: {value}
session: {session_id}
learned_ts: {ts}
source: {source}
---
"""
    try:
        path.write_text(frontmatter + "\n" + value + "\n", encoding="utf-8")
        return f"VAULT MEMORY stored: {key}"
    except Exception as exc:
        return f"ERROR: vault memory write failed: {exc}"

# ---------------------------------------------------------------------------
# Tool shortcuts (mirrors kovi main)
# ---------------------------------------------------------------------------

def search_codebase(query: str) -> str:
    gate = _dispatch_tool("search_codebase")
    if gate is not None:
        return gate
    url = (_env("SEARCH_AGENT_URL") or "http://search-agent:8082").rstrip("/") + "/search/code"
    try:
        resp = requests.post(url, json={"query": query, "k_code": 8, "k_docs": 5}, timeout=20)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body.get("results", body.get("code", str(body)))
    except Exception:
        result = _local_search(query)
        _after_tool("search_codebase", {"query": query}, result)
        return result

    _after_tool("search_codebase", {"query": query}, body.get("results", body.get("code", str(body))))
    return body.get("results", body.get("code", str(body)))

def _local_search(query: str) -> str:
    import subprocess
    try:
        cmd = ["rg", "-n", "--smart-case", query, str(REPO_ROOT)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()[:30]
            return "Local search results (rg):\n" + "\n".join(lines)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        cmd = ["grep", "-rn", "--include=*.rs", "--include=*.md", "--include=*.toml", query, str(REPO_ROOT)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()[:30]
            return "Local search results (grep):\n" + "\n".join(lines)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return f"(no local search tool available; cannot search for '{query}')"

def search_kovanica_docs(query: str) -> str:
    gate = _dispatch_tool("search_kovanica_docs")
    if gate is not None:
        return gate
    url = (_env("SEARCH_AGENT_URL") or "http://search-agent:8082").rstrip("/") + "/search/docs"
    skill_refs = Path(AGENT_DIR) / "kovanica-blockchain-developer-references"
    try:
        resp = requests.post(url, json={"query": query, "k_code": 5, "k_docs": 8}, timeout=20)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body.get("results", body.get("docs", str(body)))
    except Exception:
        result = _local_search_in_dir(query, skill_refs) if skill_refs.exists() else f"(skill docs search unavailable — no search-agent and no local references at {skill_refs})"
        _after_tool("search_kovanica_docs", {"query": query}, result)
        return result

    _after_tool("search_kovanica_docs", {"query": query}, body.get("results", body.get("docs", str(body))))
    return body.get("results", body.get("docs", str(body)))

def _local_search_in_dir(query: str, directory: Path) -> str:
    import subprocess
    try:
        cmd = ["rg", "-n", "--smart-case", query, str(directory)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()[:20]
            return "Skill docs search results (local):\n" + "\n".join(lines)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return f"(cannot search skill docs locally for '{query}')"

def read_file(path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
    gate = _dispatch_tool("read_file")
    if gate is not None:
        return gate
    full_path = REPO_ROOT / path.lstrip("/")
    if not full_path.resolve().is_relative_to(REPO_ROOT.resolve()):
        return "ERROR: path escapes repo root"
    if not full_path.is_file():
        return f"ERROR: file not found: {path}"
    with open(full_path, "r", errors="replace") as f:
        lines = f.readlines()
    end_line = end_line or len(lines)
    result = "".join(lines[start_line - 1:end_line])
    _after_tool("read_file", {"path": path, "start_line": start_line, "end_line": end_line}, result)
    return result

def run_cargo_command(command: str, args: list[str] = []) -> str:
    gate = _dispatch_tool("run_cargo_command")
    if gate is not None:
        return gate
    ALLOWED = {"check", "test", "clippy", "build"}
    if command not in ALLOWED:
        return f"REJECTED: '{command}' is not whitelisted ({sorted(ALLOWED)})"
    if _sidecar_run_cargo is not None:
        result = _sidecar_run_cargo(command, list(args), repo_path=REPOS_PATH)
        if result.startswith("ERROR: cannot reach sandbox-runner"):
            pass
        else:
            return result
    import subprocess
    cargo_cmd = ["cargo", command] + list(args)
    proc = subprocess.run(cargo_cmd, capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT))
    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        display = combined.strip()
        if display:
            result = f"cargo {command} OK:\n{display[:8000]}"
        else:
            result = f"cargo {command} OK"
    else:
        display = combined.strip()
        result = f"cargo {command} FAILED (exit {proc.returncode}):\n{display[:8000]}"
    _after_tool("run_cargo_command", {"command": command, "args": list(args)}, result)
    return result

def run_kovanica_cli(args: list[str]) -> str:
    gate = _dispatch_tool("run_kovanica_cli")
    if gate is not None:
        return gate
    if not args:
        return "REJECTED: no arguments — usage: kovi kovanica <command> [args...]"
    ALLOWED_COMMANDS = {"head", "p2p", "bootstrap", "state", "blocks", "balance", "address", "help", "--help"}
    first = args[0]
    if first not in ALLOWED_COMMANDS and first != "help":
        return f"REJECTED: '{first}' is not an allowed kovanica command. Allowed: {sorted(ALLOWED_COMMANDS)}"
    import shutil, os
    binary = shutil.which("kovanica")
    if not binary:
        candidate = os.path.join(str(REPO_ROOT), "target", "debug", "kovanica")
        if os.path.isfile(candidate):
            binary = candidate
    if binary:
        cmd = [binary] + args
    else:
        cmd = ["cargo", "run", "-p", "kovanica-cli", "--", *args]
    import subprocess
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT))
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            result = combined.strip() or f"kovanica {first} OK (no output)"
        else:
            result = f"kovanica {first} FAILED (exit {proc.returncode}):\n{combined.strip()[:4000]}"
    except subprocess.TimeoutExpired:
        result = f"kovanica {first} TIMEOUT after 60s"
    except FileNotFoundError:
        result = "ERROR: cargo not found on PATH"
    _after_tool("run_kovanica_cli", {"args": list(args)}, result)
    return result

def git_diff_suggest(path: str, explanation: str, patch: str) -> str:
    gate = _dispatch_tool("git_diff_suggest")
    if gate is not None:
        return gate
    return (
        "PROPOSED (not applied). This diff is staged for human review.\n"
        f"File: {path}\n"
        f"Why: {explanation}\n"
        f"--- patch ---\n{patch}\n"
        "To apply: use the HTTP /confirm endpoint with approve=true, or run "
        "`kovi apply --approve` after reviewing."
    )

def query_node_api(endpoint: str) -> str:
    gate = _dispatch_tool("query_node_api")
    if gate is not None:
        return gate
    node_url = _env("KOVANICA_NODE_URL", "https://explorer.kovanica.online")
    _BLOCKED = {"mine", "faucet", "submit", "operator"}
    _ALLOWED = {
        "/api/head", "/api/state", "/api/blocks", "/api/bootstrap",
        "/api/history", "/api/utxos", "/api/origins", "/metrics",
        "/api/fee_estimate",
    }
    normalised = endpoint.strip()
    if any(tok in normalised.lower() for tok in _BLOCKED):
        return f"REJECTED: endpoint '{normalised}' contains a blocked keyword ({_BLOCKED})"
    if normalised not in _ALLOWED:
        return f"REJECTED: endpoint '{normalised}' not in allowlist. Allowed: {sorted(_ALLOWED)}"
    url = f"{node_url.rstrip('/')}{normalised}"
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        result = resp.text[:4000]
    except requests.Timeout:
        result = f"ERROR: request to {url} timed out after 8s"
    except requests.ConnectionError:
        result = f"ERROR: could not connect to {url}"
    except requests.HTTPError as e:
        result = f"ERROR: HTTP {e.response.status_code} from {url}: {e.response.text[:1000]}"
    except Exception as exc:
        result = f"ERROR: {exc}"
    _after_tool("query_node_api", {"endpoint": endpoint}, result)
    return result

def explain_concept(term: str) -> str:
    gate = _dispatch_tool("explain_concept")
    if gate is not None:
        return gate
    code_results = search_codebase(f"definition and usage of {term}")
    doc_results = search_kovanica_docs(f"definition and usage of {term}")
    result = (
        f"Below are excerpts that explain or reference **{term}**, from the "
        f"Kovanica codebase and the protocol's skill/reference docs:\n\n"
        + code_results
        + "\n\n---\n\n"
        + doc_results
    )
    _after_tool("explain_concept", {"term": term}, result)
    return result

# ---------------------------------------------------------------------------
# Core chat (one turn)
# ---------------------------------------------------------------------------

def chat(message: str, session_id: str = "cli-default", role: str = "dev", verbose: bool = False, json_out: bool = False, model: str | None = None) -> str | dict[str, Any]:
    base_url, api_key, resolved_model = resolve_llm()
    effective_model = model or resolved_model
    if not base_url or base_url == "http://vllm:8000/v1":
        err = "ERROR: No LLM endpoint configured. Set one of:\n  LLM_BASE_URL=...  VLLM_BASE_URL=...  AGENT_MODEL=..."
        if json_out:
            return {"tool": "chat", "status": "error", "reply": err}
        return err

    llm = ChatOpenAI(base_url=base_url, api_key=api_key, model=effective_model, temperature=0.1, timeout=180, max_retries=1)
    user_text = message
    grounding = _grounding_context(user_text) if user_text else ""

    sys_prompt = SYSTEM_PROMPT
    if grounding:
        sys_prompt += (
            "\n\n## Retrieved context (already fetched — answer from it)\n"
            "Write a direct answer in prose. Cite file paths from this context "
            "when you use them. Do NOT emit tool-call JSON.\n\n"
            + grounding
        )

    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=user_text)]

    if verbose:
        print(f"[verbose] LLM request: model={effective_model}, turns={len(messages)}", file=sys.stderr)
        print(f"[verbose] system prompt length: {len(sys_prompt)} chars", file=sys.stderr)
        print(f"[verbose] user message length: {len(user_text)} chars", file=sys.stderr)

    try:
        response = llm.invoke(messages)
    except Exception as exc:
        err = f"ERROR: LLM call failed: {exc.__class__.__name__}: {exc}"
        if json_out:
            return {"tool": "chat", "status": "error", "reply": err}
        return err

    text = _msg_text(response)
    text = strip_fake_tool_json(text)
    if not text:
        text = "(empty response from LLM)"

    # Fire PostToolUse hooks for every tool that ran during this turn
    if _hooks:
        for tool_name, tool_args in _hooks._get_tools_run_this_turn():
            _after_tool(tool_name, tool_args, text)

    if json_out:
        return {"tool": "chat", "status": "ok", "reply": text}
    return text

def _grounding_context(question: str) -> str:
    chunks = []
    try:
        found = search_codebase(question)
        if found and found != "(code search unavailable":
            chunks.append(found[:4500])
    except Exception as exc:
        chunks.append(f"(code search unavailable: {exc.__class__.__name__})")
    try:
        found_docs = search_kovanica_docs(question)
        if found_docs and found_docs != "(skill docs search unavailable":
            chunks.append(found_docs[:3500])
    except Exception as exc:
        chunks.append(f"(skill docs search unavailable: {exc.__class__.__name__})")
    q = (question or "").lower()
    if any(h in q for h in _LIVE_HINTS):
        try:
            live = query_node_api("/api/head")
            chunks.append("Live node /api/head:\n" + str(live)[:1500])
        except Exception:
            pass
    return "\n\n".join(chunks)

# ---------------------------------------------------------------------------
# REPL main loop
# ---------------------------------------------------------------------------

def repl_main(session_id: str, role: str, verbose: bool, json_out: bool, no_vault: bool, no_auto_memory: bool, model: str | None = None):
    if _te is None:
        print("ERROR: tools_ext not available — cannot run REPL", file=sys.stderr)
        sys.exit(1)

    conv = Conversation(session_id, role, verbose, json_out, model)
    print(f"Kovanica REPL (session={session_id}, role={role}, verbose={verbose}, json={json_out}, model={model or 'inherit'})", file=sys.stderr)
    print("Type !help for inline commands, !quit to exit.", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    try:
        while True:
            try:
                line = input("kovanica> ")
            except EOFError:
                print(file=sys.stderr)
                break
            except KeyboardInterrupt:
                print(file=sys.stderr)
                continue

            line = line.strip()
            if not line:
                continue

            # --- To-do: render active tasks at turn start (whenever user types something) ---
            if _te and not line.startswith("!") and not line.startswith("/"):
                tasks = _te.task_summary(session_id)
                if tasks and not tasks.startswith("(no"):
                    print(f"\n--- Active Tasks ---\n{tasks}\n--- End Tasks ---\n", file=sys.stderr)

            # --- !-prefixed inline command ---
            if line.startswith("!"):
                parts = line[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                arg_str = parts[1] if len(parts) > 1 else ""
                arg_list = arg_str.split() if arg_str else []
                if verbose:
                    print(f"[verbose] inline command: !{cmd} {arg_str}", file=sys.stderr)

                # Handle !clear specially — reset the conversation
                if cmd == "clear":
                    conv.reset()
                    if json_out:
                        print(json.dumps({"tool": "clear", "status": "ok", "reply": "Conversation history cleared."}))
                    else:
                        print("Conversation history cleared.")
                    continue

                result = _inline_dispatch_cmd(cmd, arg_list, verbose, json_out, session_id)
                if json_out and isinstance(result, dict):
                    print(json.dumps(result))
                elif isinstance(result, str):
                    print(result)
                else:
                    print(result)
                continue

            # --- regular chat turn ---
            conv.add_user(line)

            # Auto-memory: learn preferences from user text
            if not no_auto_memory:
                _auto_memory_from_turn(line, session_id, verbose)

            reply = chat(line, session_id=session_id, role=role, verbose=verbose, json_out=json_out, model=conv.model)
            reply_text = reply if isinstance(reply, str) else reply.get("reply", "")
            conv.add_assistant(reply_text)

            if json_out and isinstance(reply, dict):
                print(json.dumps(reply))
            else:
                print(reply_text)

            if verbose:
                print(f"[verbose] turn {conv.num_turns()}: user={len(line)} chars, assistant={len(reply_text)} chars", file=sys.stderr)

    finally:
        if not no_vault:
            _write_session_to_vault(session_id, conv)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="kovanica",
        description="Kovanica REPL — interactive terminal conversation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  kovanica repl                          start interactive REPL
  kovanica repl --json                   REPL with JSON output
  kovanica repl --verbose                REPL with tool-call traces
  kovanica repl --session my-session     use a named session
  kovanica repl --role user              read-only role
  kovanica repl --no-vault               don't write session to vault
  kovanica repl --no-auto-memory         don't learn preferences automatically
""",
    )
    sub = parser.add_subparsers(dest="command")

    # repl
    p_repl = sub.add_parser("repl", help="Interactive REPL with multi-turn context")
    p_repl.add_argument("--session", default="repl-default", help="Session ID")
    p_repl.add_argument("--role", choices=["dev", "user"], default="dev", help="Role (dev = full tools)")
    p_repl.add_argument("--json", action="store_true", default=False, help="JSON output mode")
    p_repl.add_argument("--verbose", action="store_true", default=False, help="Verbose/debug mode")
    p_repl.add_argument("--no-vault", action="store_true", default=False, help="Don't write session to vault")
    p_repl.add_argument("--no-auto-memory", action="store_true", default=False, help="Don't learn preferences automatically")

    args = parser.parse_args()
    if not args.command:
        print("Kovanica by Projekt Kovanica ~Kovanica protocol", file=sys.stderr)
        parser.print_help()
        print("\nClaude Code/Codex-style tools (dev role):", file=sys.stderr)
        if _te:
            for line in _te._TOOL_REFERENCE.strip().split("\n")[1:]:
                print(f"  {line}", file=sys.stderr)
        sys.exit(0)

    if args.command == "repl":
        repl_main(
            session_id=args.session,
            role=args.role,
            verbose=args.verbose,
            json_out=args.json,
            no_vault=args.no_vault,
            no_auto_memory=args.no_auto_memory,
        )
    else:
        print(f"ERROR: unknown command {args.command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
