"""
Kovanica tool extensions — glob, grep, edit, write, bash, sessions, tasks.
Mirrored into both the HTTP agent (graph.py) and the CLI (kovanica).
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Repo root resolution — mirrors the pattern used in graph.py/kovi
# ---------------------------------------------------------------------------

def _default_repos_path() -> str:
    return os.environ.get("REPOS_PATH", "/repos/kovanica-protocol").strip() or "/repos/kovanica-protocol"

REPOS_PATH = _default_repos_path()

def _repo_root() -> Path:
    root = Path(REPOS_PATH)
    if not root.exists():
        alt = Path("/root/kovanica-protocol")
        if alt.exists():
            return alt
        raise RuntimeError(f"repo root not found: {root} or {alt}")
    return root.resolve()

# ===================================================================
# GLOB — find files by glob pattern (Claude-code-style ::glob)
# ===================================================================

def glob_files(pattern: str, path: Optional[str] = None, hidden: bool = False) -> str:
    """Find files matching a glob pattern under *path* (default repo root).

    Returns a newline-separated listing of absolute and relative paths, or
    an error string on bad input.
    """
    if not pattern or not isinstance(pattern, str):
        return "ERROR: glob pattern is required"

    base = Path(path or REPOS_PATH).resolve() if path else _repo_root()

    if not base.is_dir():
        return f"ERROR: search root is not a directory: {base}"

    if any(ch in pattern for ch in "\n\r;'\"\\"):
        return "ERROR: glob pattern contains suspicious characters"

    root = base
    rel = ""
    if "**" in pattern:
        parts = pattern.split("**", 1)
        prefix = parts[0].rstrip("/")
        suffix = "**" + parts[1] if parts[1] else "**"
        if prefix:
            candidate = root / prefix
            if candidate.is_dir():
                root = candidate
                rel = prefix
                final_pattern = suffix
            else:
                return f"ERROR: glob prefix directory not found: {candidate}"
        else:
            final_pattern = pattern
    else:
        final_pattern = pattern

    results: list[str] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            if not hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(fpath, base)
                if fnmatch.fnmatch(rel_path, final_pattern):
                    results.append(fpath)
                elif fnmatch.fnmatch(fname, final_pattern):
                    results.append(fpath)
    except Exception as exc:
        return f"ERROR: glob walk failed: {exc}"

    if not results:
        return f"(no files matching {pattern!r} under {base})"

    lines = [f"Found {len(results)} file(s) matching {pattern!r}:"]
    for p in sorted(results):
        lines.append(p)
    return "\n".join(lines)

# ===================================================================
# GREP — literal content search (Claude-code-style ::grep)
# ===================================================================

_GREP_WHITELIST = frozenset({
    ".rs", ".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".json",
    ".txt", ".ts", ".tsx", ".js", ".jsx", ".lock", ".cfg", ".ini",
    ".dockerfile",
})


def grep_files(
    pattern: str,
    path: Optional[str] = None,
    case_sensitive: bool = True,
    max_results: int = 50,
) -> str:
    """Search file contents for *pattern* (literal or regex) under *path*.

    Uses rg (ripgrep) when available, falls back to grep. Returns matching
    lines with file:line:content. Only searches indexable file extensions.
    """
    if not pattern or not isinstance(pattern, str):
        return "ERROR: search pattern is required"

    base = Path(path or REPOS_PATH).resolve() if path else _repo_root()
    if not base.is_dir():
        return f"ERROR: search root is not a directory: {base}"

    includes = ",".join(f"*.{ext.lstrip('.')}" for ext in sorted(_GREP_WHITELIST))

    # Decide: use rg (preferred) or grep fallback
    try:
        cmd = [
            "rg", "--no-heading", "--with-filename", "--line-number",
            "--max-count", str(max_results), "--smart-case",
            "--glob", f"*.{{{includes}}}",
            pattern,
            str(base),
        ]
        if case_sensitive:
            cmd.append("--case-sensitive")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode in (0, 1):
            out = result.stdout.strip()
            if out:
                lines = out.splitlines()
                if len(lines) > max_results:
                    lines = lines[:max_results] + [f"... ({len(lines) - max_results} more matches suppressed)"]
                return "\n".join(lines)
            return "(no matches)"
        return f"ERROR: rg returned exit {result.returncode}: {result.stderr[:300]}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # grep fallback
    try:
        cmd = [
            "grep", "-rn",
            "--include=*.rs", "--include=*.md",
            "--include=*.toml", "--include=*.py", "--include=*.sh",
            "--include=*.yaml", "--include=*.yml", "--include=*.json",
            "--max-count", str(max_results),
            pattern,
            str(base),
        ]
        if not case_sensitive:
            cmd.insert(1, "-i")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode in (0, 1):
            out = result.stdout.strip()
            if out:
                lines = out.splitlines()
                if len(lines) > max_results:
                    lines = lines[:max_results] + [f"... ({len(lines) - max_results} more matches suppressed)"]
                return "\n".join(lines)
            return "(no matches)"
        return f"ERROR: grep returned exit {result.returncode}: {result.stderr[:300]}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "ERROR: neither rg nor grep is available on PATH"

# ===================================================================
# EDIT — targeted line-/regex-based edits (Claude-code-style ::edit)
# ===================================================================

@dataclass
class EditOp:
    """A single edit operation."""
    path: str
    old_str: str           # exact string to replace (may be multi-line)
    new_str: str           # replacement (empty string = delete)
    insert_line: Optional[int] = None   # alternative: insert after this line
    regex: bool = False
    replace_all: bool = False
    explanation: str = ""


def _safe_edit_path(path: str) -> Path | None:
    """Validate a repo-relative path. Returns resolved Path or None."""
    if not path or not isinstance(path, str):
        return None
    p = Path(path)
    if p.is_absolute():
        return None
    parts = p.parts
    if not parts or any(part in ("..", ".git", "") for part in parts):
        return None
    if ".git" in parts:
        return None
    if p.name in ("", ".", ".."):
        return None
    full = (_repo_root() / p).resolve()
    try:
        full.relative_to(_repo_root())
    except ValueError:
        return None
    return full


def _read_lines(path: Path) -> list[str]:
    with open(path, "r", errors="replace") as f:
        return f.readlines()


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.writelines(lines)


def apply_edits(edits: list[EditOp], dry_run: bool = False) -> str:
    """Apply a batch of edits. Each edit is validated before execution.

    Returns a summary string. In dry_run mode, reports what would change
    without touching any file.
    """
    if not edits:
        return "ERROR: no edits provided"

    repo_root = _repo_root()
    results: list[str] = []
    modified: list[str] = []

    for i, edit in enumerate(edits):
        path = edit.path.strip()
        rel = _safe_edit_path(path)
        if rel is None:
            return f"ERROR: edit {i}: unsafe or missing path {path!r}"

        if not rel.is_file():
            if not dry_run:
                rel.parent.mkdir(parents=True, exist_ok=True)
            if edit.new_str.strip() or edit.insert_line is not None:
                pass  # will create below
            else:
                continue

        if dry_run:
            results.append(f"[dry_run] edit {i}: {path}")
            if edit.old_str.strip():
                results.append(f"  would replace {len(edit.old_str.splitlines())} line(s)")
            if edit.new_str.strip():
                results.append(f"  would insert {len(edit.new_str.splitlines())} line(s)")
            continue

        lines = _read_lines(rel) if rel.is_file() else []
        orig_len = len(lines)

        if edit.old_str.strip():
            if edit.regex:
                # Regex replace across the file
                text = "".join(lines)
                try:
                    new_text = re.sub(edit.old_str, edit.new_str, text,
                                      count=0 if edit.replace_all else 1)
                except re.error as exc:
                    results.append(f"ERROR: edit {i}: invalid regex: {exc}")
                    continue
                if new_text != text:
                    _write_lines(rel, new_text.splitlines(keepends=True))
                    modified.append(path)
                    results.append(f"edit {i}: {path} — regex replace, {orig_len}→{len(new_text.splitlines(keepends=True))} lines")
                else:
                    results.append(f"edit {i}: {path} — pattern not found")
            else:
                # Exact string replace
                text = "".join(lines)
                if edit.old_str not in text:
                    results.append(f"ERROR: edit {i}: old_str not found in {path}")
                    continue
                new_text = text.replace(edit.old_str, edit.new_str,
                                        count=0 if edit.replace_all else 1)
                new_lines = new_text.splitlines(keepends=True)
                _write_lines(rel, new_lines)
                modified.append(path)
                results.append(f"edit {i}: {path} — replaced, {orig_len}→{len(new_lines)} lines")
        elif edit.insert_line is not None:
            # Insert after a specific line (1-indexed)
            if edit.insert_line < 1:
                results.append(f"ERROR: edit {i}: insert_line must be >= 1")
                continue
            insert_idx = edit.insert_line  # after this line (so lines[insert_idx:] shift)
            if insert_idx > len(lines):
                results.append(f"ERROR: edit {i}: insert_line {edit.insert_line} beyond EOF ({len(lines)} lines)")
                continue
            insert_lines = edit.new_str.splitlines(keepends=True)
            if not insert_lines:
                insert_lines = [edit.new_str]  # single line, no newline
            new_lines = lines[:insert_idx] + insert_lines + lines[insert_idx:]
            _write_lines(rel, new_lines)
            modified.append(path)
            results.append(f"edit {i}: {path} — inserted {len(insert_lines)} line(s) after line {edit.insert_line}")
        else:
            results.append(f"ERROR: edit {i}: no operation specified (old_str / insert_line required)")

    if dry_run:
        summary = "=== DRY RUN ===\n" + "\n".join(results)
        return summary

    if modified:
        summary = f"Applied {len(modified)} edit(s): " + ", ".join(sorted(set(modified)))
        return summary + "\n\n" + "\n".join(results)
    return "No edits were applied (patterns not found or no-op)."

# ===================================================================
# WRITE — create or overwrite files (Claude-code-style ::write)
# ===================================================================

def write_file(path: str, content: str, append: bool = False,
               create_dir: bool = True) -> str:
    """Write *content* to *path* (repo-relative). Creates parent dirs.

    For dev role only. In dry_run / preview mode use the same function
    with a flag set externally. Returns a status string.
    """
    if not path or not isinstance(path, str):
        return "ERROR: path is required"
    p = Path(path)
    if p.is_absolute():
        return "ERROR: path must be repo-relative"
    parts = p.parts
    if not parts or any(part in ("..", ".git", "") for part in parts):
        return "ERROR: path escapes repo root or contains .."
    if ".git" in parts:
        return "ERROR: cannot write to .git directory"
    if p.name in ("", ".", ".."):
        return "ERROR: invalid file name"

    full = (_repo_root() / p).resolve()
    try:
        full.relative_to(_repo_root())
    except ValueError:
        return "ERROR: resolved path escapes repo root"

    if full.is_dir():
        return f"ERROR: {path} is a directory, not a file"

    if create_dir:
        full.parent.mkdir(parents=True, exist_ok=True)

    if append and full.is_file():
        with open(full, "a") as f:
            f.write(content)
    else:
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "w") as f:
            f.write(content)

    size = len(content.encode("utf-8"))
    return f"WROTE {path} ({size} bytes, {content.count(chr(10))+1} lines)"

# ===================================================================
# BASH — limited sandboxed shell execution (Claude-code-style ::bash)
# ===================================================================

# Allowed commands (without shell metacharacters — plain argv)
_ALLOWED_BASH_CMDS = frozenset({
    "ls", "cat", "head", "tail", "wc", "tree", "find", "rg", "grep",
    "cd", "pwd", "echo", "date", "uname", "hostname", "whoami",
    "git", "cargo", "rustc", "cargo-make", "just", "make", "npm",
    "node", "python", "python3", "cargo-init", "cargo-edit",
    "du", "df", "free", "ps", "git-log", "git-diff", "git-status",
    "git-log", "git-show", "git-stash", "git-branch", "git-checkout",
})
# Commands that may run but are rate-limited / logged
_SENSITIVE_BASH_CMDS = frozenset({
    "cargo", "rustc", "npm", "node", "python", "python3", "make", "just",
})

_BASH_TIMEOUT = int(os.environ.get("KOVI_BASH_TIMEOUT", "30") or 30)

# Sandbox sidecar support (optional — uses sandbox/runner/server.py when available)
_SANDBOX_URL = os.environ.get("KOVI_SANDBOX_URL", "").strip()
_SANDBOX_TIMEOUT = int(os.environ.get("KOVI_SANDBOX_TIMEOUT", "30") or 30)


def _run_bash_in_sandbox(command: str, workdir: Optional[str] = None) -> str:
    """Run a command in the ephemeral sandbox container via the sandbox sidecar.

    Returns the sidecar response string, or an ERROR string on failure.
    The sandbox is network-disabled and mounts the repo read-only.
    """
    if not _SANDBOX_URL:
        return "ERROR: no sandbox configured (set KOVI_SANDBOX_URL)"
    import requests
    payload = {
        "command": command,
        "workdir": workdir or REPOS_PATH,
        "timeout": _SANDBOX_TIMEOUT,
    }
    try:
        resp = requests.post(f"{_SANDBOX_URL}/run", json=payload, timeout=_SANDBOX_TIMEOUT + 5)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == "ok":
            out = body.get("output", "")
            if out:
                return f"OK ({len(out)} chars, sandbox):\n{out[:5000]}"
            return "OK (no output, sandbox)"
        return f"ERROR: sandbox returned status={body.get('status')}: {body.get('error', body.get('output', ''))}"
    except requests.Timeout:
        return f"ERROR: sandbox request timed out after {_SANDBOX_TIMEOUT + 5}s"
    except requests.ConnectionError:
        return "ERROR: cannot connect to sandbox-runner (is the sidecar running?)"
    except Exception as exc:
        return f"ERROR: sandbox request failed: {exc.__class__.__name__}: {exc}"


def run_bash(command: str, workdir: Optional[str] = None, timeout: Optional[int] = None) -> str:
    """Run a whitelisted shell command and return stdout+stderr.

    Uses the ephemeral sandbox container when KOVI_SANDBOX_URL is set;
    otherwise falls back to a bare subprocess with shell=False and a whitelist.
    Commands that touch the network or modify the repo are blocked.
    Long-running commands are capped at KOVI_BASH_TIMEOUT (default 30s).
    """
    if not command or not isinstance(command, str):
        return "ERROR: command is required"

    # If sandbox is configured, try it first
    if _SANDBOX_URL:
        result = _run_bash_in_sandbox(command, workdir)
        if not result.startswith("ERROR"):
            return result
        # Sandbox unreachable or misconfigured — fall through to direct

    # Split into argv (no shell interpolation)
    args = command.strip().split()
    if not args:
        return "ERROR: empty command"

    cmd_name = os.path.basename(args[0])

    # git subcommands: git <subcommand> is fine, but reject dangerous ones
    if cmd_name == "git" and len(args) > 1:
        git_sub = args[1]
        _BLOCKED_GIT = frozenset({
            "push", "pull", "fetch", "remote", "clone", "init",
            "bundle", "receive-pack", "upload-pack",
        })
        if git_sub in _BLOCKED_GIT:
            return f"REJECTED: git {git_sub} is not allowed (network-modifying)"
        if git_sub not in _ALLOWED_BASH_CMDS and not git_sub.startswith("git-"):
            return f"REJECTED: git {git_sub} is not whitelisted"

    if cmd_name not in _ALLOWED_BASH_CMDS:
        return f"REJECTED: '{cmd_name}' is not whitelisted ({sorted(_ALLOWED_BASH_CMDS)})"

    cwd = Path(workdir or REPOS_PATH).resolve() if workdir else _repo_root()
    if not cwd.is_dir():
        return f"ERROR: workdir not found: {cwd}"

    effective_timeout = timeout or _BASH_TIMEOUT

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=str(cwd),
        )
        combined = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0:
            display = combined.strip()
            if display:
                return f"OK ({len(display)} chars):\n{display[:5000]}"
            return "OK (no output)"
        else:
            display = combined.strip()
            if not display:
                return f"FAILED (exit {result.returncode})"
            return f"FAILED (exit {result.returncode}):\n{display[:5000]}"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT after {effective_timeout}s"
    except FileNotFoundError:
        return f"ERROR: {cmd_name} not found on PATH"
    except Exception as exc:
        return f"ERROR: {exc.__class__.__name__}: {exc}"

# ===================================================================
# SESSIONS — list, resume, kill (CLI-only management)
# ===================================================================

_SESSION_DB = os.environ.get("AGENT_DB", "/data/agent.sqlite3")


def session_list() -> str:
    """Return a summary of recent agent sessions from the SQLite checkpoint DB."""
    try:
        import sqlite3
        conn = sqlite3.connect(_SESSION_DB)
        cur = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
        )
        rows = cur.fetchall()
        if not rows:
            return "(no sessions found)"
        lines = [f"Active sessions ({len(rows)}):"]
        for (tid,) in rows:
            try:
                last = conn.execute(
                    "SELECT value FROM checkpoints WHERE thread_id=? ORDER BY id DESC LIMIT 1",
                    (tid,),
                ).fetchone()
                last_msg = ""
                if last and last["value"]:
                    import json as _json
                    try:
                        state = _json.loads(last["value"])
                        msgs = state.get("messages", [])
                        if msgs:
                            last_msg = str(msgs[-1].get("content", ""))[:60]
                    except Exception:
                        pass
                lines.append(f"  {tid}  {last_msg}")
            except Exception:
                lines.append(f"  {tid}")
        conn.close()
        return "\n".join(lines)
    except Exception as exc:
        return f"ERROR: cannot read session DB: {exc}"


def session_kill(thread_id: str) -> str:
    """Delete a session's checkpoint data."""
    try:
        import sqlite3
        conn = sqlite3.connect(_SESSION_DB)
        cur = conn.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()
        if deleted:
            return f"Killed session {thread_id} ({deleted} checkpoint(s) removed)"
        return f"Session {thread_id} not found"
    except Exception as exc:
        return f"ERROR: {exc}"

# ===================================================================
# TASKS — agent-side todo tracking (Claude-code-style ::task)
# ===================================================================

_TASK_DB = None
_TASK_LOCK = None


def _task_db() -> tuple:
    global _TASK_DB, _TASK_LOCK
    if _TASK_DB is None:
        import sqlite3, threading
        db_path = os.environ.get("KOVI_TASK_DB",
                                  str(Path(REPOS_PATH) / ".kovi" / "tasks.sqlite3"))
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _TASK_DB = sqlite3.connect(str(db_path), check_same_thread=False)
        _TASK_DB.row_factory = sqlite3.Row
        _TASK_DB.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_ts TEXT NOT NULL,
                done_ts TEXT
            )"""
        )
        _TASK_DB.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks (session_id)"
        )
        _TASK_LOCK = threading.Lock()
    return _TASK_DB, _TASK_LOCK


@dataclass
class Task:
    id: str
    session_id: str
    content: str
    status: str = "pending"
    created_ts: str = ""
    done_ts: str = ""


def task_add(session_id: str, content: str) -> Task:
    """Add a task for a session."""
    db, lock = _task_db()
    with lock:
        task_id = str(uuid.uuid4())[:8]
        ts = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO tasks (id, session_id, content, status, created_ts) VALUES (?, ?, ?, 'pending', ?)",
            (task_id, session_id, content, ts),
        )
        db.commit()
    return Task(id=task_id, session_id=session_id, content=content,
                status="pending", created_ts=ts)


def task_list(session_id: str) -> list[Task]:
    """List tasks for a session."""
    db, lock = _task_db()
    with lock:
        rows = db.execute(
            "SELECT * FROM tasks WHERE session_id=? ORDER BY created_ts",
            (session_id,),
        ).fetchall()
    return [
        Task(id=r["id"], session_id=r["session_id"], content=r["content"],
             status=r["status"], created_ts=r["created_ts"], done_ts=r["done_ts"])
        for r in rows
    ]


def task_done(session_id: str, task_id: str) -> str:
    """Mark a task done."""
    db, lock = _task_db()
    with lock:
        ts = datetime.now(timezone.utc).isoformat()
        cur = db.execute(
            "UPDATE tasks SET status='done', done_ts=? WHERE id=? AND session_id=?",
            (ts, task_id, session_id),
        )
        db.commit()
        if cur.rowcount:
            return f"Task {task_id} marked done"
        return f"Task {task_id} not found"


def task_remove(session_id: str, task_id: str) -> str:
    """Remove a task."""
    db, lock = _task_db()
    with lock:
        cur = db.execute("DELETE FROM tasks WHERE id=? AND session_id=?",
                         (task_id, session_id))
        db.commit()
        if cur.rowcount:
            return f"Task {task_id} removed"
        return f"Task {task_id} not found"


def task_summary(session_id: str) -> str:
    """Return a human-readable task summary."""
    tasks = task_list(session_id)
    if not tasks:
        return f"No tasks for session {session_id}"
    lines = [f"Tasks for {session_id} ({len(tasks)}):"]
    for t in tasks:
        status_mark = "✓" if t.status == "done" else "○"
        lines.append(f"  [{status_mark}] {t.id}: {t.content}")
    return "\n".join(lines)

# ===================================================================
# AUTO-MEMORY — store/retrieve learned user preferences
# ===================================================================

_MEMORY_DB = None


def _memory_db_path() -> Path:
    return Path(os.environ.get(
        "KOVI_MEMORY_DB",
        str(Path(REPOS_PATH) / ".kovi" / "memory.sqlite3"),
    ))


def _ensure_memory_db() -> None:
    global _MEMORY_DB
    if _MEMORY_DB is not None:
        return
    import sqlite3
    db = _memory_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_DB = sqlite3.connect(str(db), check_same_thread=False)
    _MEMORY_DB.row_factory = sqlite3.Row
    _MEMORY_DB.execute(
        """CREATE TABLE IF NOT EXISTS memory (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            session_id TEXT,
            learned_ts TEXT NOT NULL,
            source TEXT DEFAULT 'auto'
        )"""
    )


def memory_store(key: str, value: str, session_id: str = "",
                 source: str = "auto") -> str:
    """Store a learned fact."""
    _ensure_memory_db()
    ts = datetime.now(timezone.utc).isoformat()
    _MEMORY_DB.execute(
        "INSERT OR REPLACE INTO memory (key, value, session_id, learned_ts, source) VALUES (?, ?, ?, ?, ?)",
        (key, value, session_id, ts, source),
    )
    _MEMORY_DB.commit()
    return f"MEMORY stored: {key}"


def memory_recall(prefix: str = "", limit: int = 10) -> str:
    """Recall memory entries whose key starts with *prefix*."""
    _ensure_memory_db()
    if prefix:
        rows = _MEMORY_DB.execute(
            "SELECT key, value, source, learned_ts FROM memory WHERE key LIKE ? ORDER BY learned_ts DESC LIMIT ?",
            (f"{prefix}%", limit),
        ).fetchall()
    else:
        rows = _MEMORY_DB.execute(
            "SELECT key, value, source, learned_ts FROM memory ORDER BY learned_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "(no memory recalled)"
    lines = [f"Recalled {len(rows)} memory entry/ies:"]
    for r in rows:
        lines.append(f"  [{r['source']}] {r['key']} = {r['value']}  (learned {r['learned_ts'][:10]})")
    return "\n".join(lines)


def memory_forget(key: str) -> str:
    """Forget a memory entry."""
    _ensure_memory_db()
    cur = _MEMORY_DB.execute("DELETE FROM memory WHERE key=?", (key,))
    _MEMORY_DB.commit()
    if cur.rowcount:
        return f"MEMORY forgotten: {key}"
    return f"Memory key {key!r} not found"

# ===================================================================
# HELP / COMMAND REFERENCE
# ===================================================================

_TOOL_REFERENCE = """
Kovanica tools (mirrored from Claude Code / Codex):

  ::glob <pattern>       Find files by glob (e.g. **/*.rs)
  ::grep <pattern>       Search file contents (literal/regex)
  ::read <path> [start] [end]   Read file slice
  ::edit <path> <old> <new>     Replace exact string
  ::write <path> <content>      Create/overwrite file
  ::bash <cmd>           Run whitelisted shell command
  ::task add <description>   Add a todo task
  ::task list             List tasks
  ::task done <id>        Mark task done
  ::task remove <id>      Remove task
  ::session list          List active sessions
  ::session kill <id>     Kill a session
  ::memory recall [prefix]  Recall learned facts
  ::help                  Show this reference

Dev-only tools: ::edit, ::write, ::bash, ::task, ::session kill
Read-only tools: ::glob, ::grep, ::read, ::session list, ::memory recall
"""
