"""
Kovanica subagent registry — definitions, spawn, status, return-gating.

Mirrors Claude Code's subagent system:
- Each subagent has its own description, tool set, model, system prompt
- Spawn creates an isolated subagent that runs on a task and returns a result
- SubagentStop hook enforces return gates (e.g. "tests must pass before folding back")
- Nesting depth capped at 5
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Subagent definition
# ---------------------------------------------------------------------------

@dataclass
class SubagentDef:
    name: str
    description: str
    tools: list[str]                # tool names this subagent may call
    model: str | None = None       # overrides parent model when set
    system_prompt: str = ""        # additional prompt injected for this subagent
    max_turns: int = 20            # hard cap on turns before forced stop
    permission_mode: str = "auto"  # permission mode this subagent runs under


# Built-in subagent definitions ( mirrors Claude Code's subagent catalog )
SUBAGENT_CATALOG: dict[str, SubagentDef] = {
    "code-reviewer": SubagentDef(
        name="code-reviewer",
        description="Reviews code for correctness, style, and consensus safety.",
        tools=["read_file", "grep", "search_codebase", "explain_concept", "git_diff_suggest"],
        model=None,
        system_prompt="You are a code reviewer. Be precise. Cite file paths. Flag consensus-critical issues first.",
        max_turns=30,
        permission_mode="auto",
    ),
    "test-engineer": SubagentDef(
        name="test-engineer",
        description="Writes and runs tests, property tests, and adversarial tests.",
        tools=["read_file", "grep", "search_codebase", "run_cargo_command", "explain_concept"],
        model=None,
        system_prompt="You are a test engineer. Write tests before claiming they pass. Target invariants, not implementation details.",
        max_turns=40,
        permission_mode="auto",
    ),
    "security-auditor": SubagentDef(
        name="security-auditor",
        description="Audits crypto, consensus, and input handling for vulnerabilities.",
        tools=["read_file", "grep", "search_codebase", "explain_concept"],
        model=None,
        system_prompt="You are a security auditor. Focus on consensus determinism, crypto usage, and untrusted input parsing. Severity: Critical > High > Medium > Low.",
        max_turns=30,
        permission_mode="auto",
    ),
    "doc-writer": SubagentDef(
        name="doc-writer",
        description="Writes and updates technical documentation in the vault.",
        tools=["read_file", "grep", "search_codebase", "write_file", "explain_concept"],
        model=None,
        system_prompt="You are a documentation writer. Prefer precise, verifiable statements. Do not invent APIs or paths.",
        max_turns=30,
        permission_mode="auto",
    ),
    "api-designer": SubagentDef(
        name="api-designer",
        description="Designs and evolves node RPC, explorer, and wallet APIs.",
        tools=["read_file", "grep", "search_codebase", "explain_concept", "git_diff_suggest"],
        model=None,
        system_prompt="You are an API designer. Resource-oriented names, pagination for unbounded results, RFC 7807 errors, OpenAPI spec as source of truth.",
        max_turns=30,
        permission_mode="auto",
    ),
    "migration-engineer": SubagentDef(
        name="migration-engineer",
        description="Plans and executes store schema migrations and protocol upgrades.",
        tools=["read_file", "grep", "search_codebase", "run_cargo_command", "explain_concept"],
        model=None,
        system_prompt="You are a migration engineer. Idempotent, batched, atomic version bump. Backup before every migration. Rollback plan required before deploy.",
        max_turns=30,
        permission_mode="auto",
    ),
    "performance-engineer": SubagentDef(
        name="performance-engineer",
        description="Benchmarks and profiles hot paths.",
        tools=["read_file", "grep", "search_codebase", "run_cargo_command", "explain_concept"],
        model=None,
        system_prompt="You are a performance engineer. Never optimize without a measurement. Micro-benchmarks lie about cache effects — validate with a real node run.",
        max_turns=30,
        permission_mode="auto",
    ),
    "release-engineer": SubagentDef(
        name="release-engineer",
        description="Tags, builds, changelogs, and publishes releases.",
        tools=["read_file", "grep", "search_codebase", "run_cargo_command", "git_diff_suggest"],
        model=None,
        system_prompt="You are a release engineer. SemVer. Changelog before tag. Tag before release. Draft PR before merge.",
        max_turns=30,
        permission_mode="auto",
    ),
    "devops-engineer": SubagentDef(
        name="devops-engineer",
        description="CI/CD, monitoring, infrastructure.",
        tools=["read_file", "grep", "search_codebase", "run_cargo_command", "bash"],
        model=None,
        system_prompt="You are a DevOps engineer. CI/CD: build matrix, test stages, lint/format, security audit. Monitoring: Prometheus, structured logging, alerting.",
        max_turns=30,
        permission_mode="auto",
    ),
    "vault-sync": SubagentDef(
        name="vault-sync",
        description="Syncs documentation between kovanica-protocol source and vault snapshots.",
        tools=["read_file", "grep", "search_codebase", "write_file", "explain_concept"],
        model=None,
        system_prompt="You are a vault sync agent. Keep vault snapshots in sync with /root/kovanica-protocol. Prefer the current merged layout over old snapshots when they disagree.",
        max_turns=30,
        permission_mode="auto",
    ),
}

_SUBAGENT_CATALOG_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Running subagent state
# ---------------------------------------------------------------------------

@dataclass
class SubagentRun:
    id: str
    name: str
    parent_session: str
    task: str
    status: str = "pending"          # pending | running | stopped | returned
    result: Any = None
    turns: int = 0
    started_at: float = field(default_factory=time.time)
    stopped_at: float | None = None
    permission_mode: str = "auto"
    model: str | None = None


# In-memory store for running subagents (per session)
_RUNNING_SUBAGENTS: dict[str, SubagentRun] = {}
_RUNNING_SUBAGENTS_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Spawn / status / result
# ---------------------------------------------------------------------------

def list_subagents() -> list[dict]:
    with _SUBAGENT_CATALOG_LOCK:
        return [
            {
                "name": s.name,
                "description": s.description,
                "tools": s.tools,
                "model": s.model,
                "max_turns": s.max_turns,
                "permission_mode": s.permission_mode,
            }
            for s in SUBAGENT_CATALOG.values()
        ]


def spawn_subagent(
    name: str,
    task: str,
    parent_session: str = "cli-default",
    model: str | None = None,
    permission_mode: str | None = None,
) -> dict:
    """Spawn a subagent. Returns a subagent handle dict."""
    with _SUBAGENT_CATALOG_LOCK:
        defn = SUBAGENT_CATALOG.get(name)
    if defn is None:
        return {"error": f"unknown subagent {name!r}"}

    run_id = f"sub-{name}-{int(time.time())}-{os.urandom(2).hex()}"
    run = SubagentRun(
        id=run_id,
        name=name,
        parent_session=parent_session,
        task=task,
        status="pending",
        permission_mode=permission_mode or defn.permission_mode,
        model=model or defn.model,
    )
    with _RUNNING_SUBAGENTS_LOCK:
        _RUNNING_SUBAGENTS[run_id] = run

    return {
        "id": run_id,
        "name": name,
        "parent_session": parent_session,
        "task": task,
        "status": "pending",
        "permission_mode": run.permission_mode,
        "model": run.model,
        "max_turns": defn.max_turns,
        "description": defn.description,
    }


def get_subagent(run_id: str) -> dict | None:
    with _RUNNING_SUBAGENTS_LOCK:
        run = _RUNNING_SUBAGENTS.get(run_id)
    if run is None:
        return None
    return {
        "id": run.id,
        "name": run.name,
        "parent_session": run.parent_session,
        "task": run.task,
        "status": run.status,
        "result": run.result,
        "turns": run.turns,
        "started_at": run.started_at,
        "stopped_at": run.stopped_at,
        "permission_mode": run.permission_mode,
        "model": run.model,
    }


def list_running_subagents(session: str = "cli-default") -> list[dict]:
    with _RUNNING_SUBAGENTS_LOCK:
        runs = [
            r for r in _RUNNING_SUBAGENTS.values()
            if r.parent_session == session
        ]
    return [
        {
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "turns": r.turns,
            "started_at": r.started_at,
            "permission_mode": r.permission_mode,
            "model": r.model,
        }
        for r in runs
    ]


def stop_subagent(run_id: str) -> dict:
    with _RUNNING_SUBAGENTS_LOCK:
        run = _RUNNING_SUBAGENTS.get(run_id)
        if run is None:
            return {"error": f"subagent {run_id!r} not found"}
        run.status = "stopped"
        run.stopped_at = time.time()
    return {"status": "stopped", "id": run_id}


def return_subagent_result(run_id: str, result: Any) -> dict:
    """Mark a subagent as returned with *result*. Fires SubagentStop hooks."""
    from agent.hooks import _fire_subagent_stop

    with _RUNNING_SUBAGENTS_LOCK:
        run = _RUNNING_SUBAGENTS.get(run_id)
        if run is None:
            return {"error": f"subagent {run_id!r} not found"}
        run.status = "returned"
        run.result = result
        run.stopped_at = time.time()

    gated_result = _fire_subagent_stop(run.name, result)
    return {
        "status": "returned",
        "id": run_id,
        "name": run.name,
        "result": gated_result,
    }
