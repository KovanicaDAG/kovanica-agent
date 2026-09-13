"""
Kovanica permission modes — manual / acceptEdits / auto / plan.

Mirrors Claude Code's permission-mode classifier:
- manual: prompt the user before every tool use (default for untrusted contexts)
- acceptEdits: auto-approve file edits, still prompt for bash
- auto: classifier reviews each action (read-only / low-risk = auto-approve)
- plan: no execution or editing at all — analysis only
"""

from __future__ import annotations

import os
import threading
from typing import Literal

Mode = Literal["manual", "acceptEdits", "auto", "plan"]

# Default: manual — mirrors Claude Code's out-of-the-box default
_MODE: Mode = "manual"
_MODE_LOCK = threading.Lock()

# Tools that are always safe under `auto` (read-only, no repo mutation, no shell)
_ALWAYS_AUTO = frozenset({
    "search_codebase", "search_kovanica_docs", "read_file",
    "explain_concept", "query_node_api", "glob", "grep",
    "memory_recall", "session_list",
})

# Tools that require explicit approval even under `auto`
_APPROVAL_REQUIRED = frozenset({
    "edit", "write", "bash", "run_cargo_command",
    "git_diff_suggest", "run_kovanica_cli",
    "task_add", "task_done", "task_remove",
    "session_kill", "memory_store", "memory_forget",
})


def set_mode(mode: Mode) -> Mode:
    global _MODE
    with _MODE_LOCK:
        _MODE = mode
    return _MODE


def get_mode() -> Mode:
    with _MODE_LOCK:
        return _MODE


def check(tool_name: str) -> tuple[bool, str]:
    """Return (allowed, reason). Called by the tool dispatcher before every tool use."""
    with _MODE_LOCK:
        m = _MODE

    if m == "plan":
        return False, "plan mode: no execution or editing allowed"

    if m == "manual":
        return True, "manual mode: will prompt if needed"

    if m == "acceptEdits":
        if tool_name in _ALWAYS_AUTO:
            return True, "acceptEdits: auto-approved (read-only)"
        if tool_name in _APPROVAL_REQUIRED and tool_name in ("edit", "write"):
            return True, "acceptEdits: auto-approved (file edit)"
        return True, "acceptEdits: will prompt for non-edit tools"

    if m == "auto":
        if tool_name in _ALWAYS_AUTO:
            return True, "auto: auto-approved (read-only)"
        if tool_name in _APPROVAL_REQUIRED:
            return False, "auto: requires approval (mutates repo / runs shell / runs cargo)"
        return True, "auto: auto-approved"

    return True, f"unknown mode {m!r} — allowing"


def can_run(tool_name: str) -> bool:
    allowed, _ = check(tool_name)
    return allowed
