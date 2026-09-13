"""
Kovanica hooks — lifecycle event hooks (PreToolUse, PostToolUse, Stop, SubagentStop).

Mirrors Claude Code's hook system:
- PreToolUse: before a tool runs; can modify args or raise to block
- PostToolUse: after a tool returns; can inspect/transform result
- Stop: fired when the agent loop stops
- SubagentStop: fired when a subagent finishes; enforces return gates
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------

@dataclass
class HookSpec:
    name: str                      # SubagentStop, PreToolUse, PostToolUse, Stop
    hook: Callable                 # async or sync function
    agent: str | None = None       # which subagent this applies to (None = all)
    trigger: str = "default"       # when it fires relative to the tool call

# Global registry — populated by `kovi hooks add` and by skill-side declarations
_HOOKS: list[HookSpec] = []
_HOOKS_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Built-in hook points (called by the agent loop)
# ---------------------------------------------------------------------------

def _fire_pre_tool_use(tool_name: str, tool_args: dict) -> dict | None:
    """Run PreToolUse hooks. Return mutated args dict, or None to block."""
    mutated = dict(tool_args)
    with _HOOKS_LOCK:
        for h in _HOOKS:
            if h.name != "PreToolUse":
                continue
            if h.agent is not None:
                continue  # subagent-scoped hooks fire in subagent context
            try:
                out = h.hook(tool_name, tool_args, mutated)
            except Exception as e:
                print(f"[hooks] PreToolUse {h.name} raised: {e}", file=sys.stderr)
                continue
            if out is None:
                return None  # hook blocked the tool
            if isinstance(out, dict):
                mutated.update(out)
    return mutated


def _fire_post_tool_use(tool_name: str, tool_args: dict, result: Any) -> None:
    with _HOOKS_LOCK:
        for h in _HOOKS:
            if h.name != "PostToolUse":
                continue
            if h.agent is not None:
                continue
            try:
                h.hook(tool_name, tool_args, result)
            except Exception as e:
                print(f"[hooks] PostToolUse {h.name} raised: {e}", file=sys.stderr)


def _fire_stop() -> None:
    with _HOOKS_LOCK:
        for h in _HOOKS:
            if h.name != "Stop":
                continue
            try:
                h.hook()
            except Exception as e:
                print(f"[hooks] Stop {h.name} raised: {e}", file=sys.stderr)


def _fire_subagent_stop(subagent_name: str, subagent_result: Any) -> Any:
    """Run SubagentStop hooks for *subagent_name*. Return the (possibly gated) result."""
    with _HOOKS_LOCK:
        for h in _HOOKS:
            if h.name != "SubagentStop":
                continue
            if h.agent is not None and h.agent != subagent_name:
                continue
            try:
                out = h.hook(subagent_name, subagent_result)
            except Exception as e:
                print(f"[hooks] SubagentStop {h.name} raised: {e}", file=sys.stderr)
                continue
            if out is not None:
                subagent_result = out
    return subagent_result


# ---------------------------------------------------------------------------
# CLI-exposed helpers
# ---------------------------------------------------------------------------

def list_hooks() -> list[dict]:
    with _HOOKS_LOCK:
        return [
            {
                "name": h.name,
                "agent": h.agent,
                "trigger": h.trigger,
            }
            for h in _HOOKS
        ]


def add_hook(name: str, agent: str | None, trigger: str, hook_path: str) -> dict:
    """Register a hook from a Python file on disk. The file must expose a
    callable named `hook` (sync or async)."""
    path = pathlib.Path(hook_path)
    if not path.is_file():
        return {"error": f"hook file not found: {hook_path}"}
    try:
        spec = importlib.util.spec_from_file_location("hook_mod", path)
        if spec is None or spec.loader is None:
            return {"error": f"cannot load hook module from {hook_path}"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        return {"error": f"failed to load hook {hook_path}: {e}"}
    if not hasattr(mod, "hook"):
        return {"error": f"hook {hook_path} has no `hook` callable"}
    with _HOOKS_LOCK:
        _HOOKS.append(HookSpec(name=name, agent=agent, trigger=trigger, hook=mod.hook))
    return {"status": "added", "name": name, "agent": agent, "trigger": trigger}


def remove_hook(name: str, agent: str | None = None) -> dict:
    with _HOOKS_LOCK:
        before = len(_HOOKS)
        _HOOKS[:] = [
            h for h in _HOOKS
            if not (h.name == name and (agent is None or h.agent == agent))
        ]
        removed = before - len(_HOOKS)
    return {"status": "removed", "removed": removed}


def clear_hooks() -> dict:
    with _HOOKS_LOCK:
        n = len(_HOOKS)
        _HOOKS.clear()
    return {"status": "cleared", "removed": n}
