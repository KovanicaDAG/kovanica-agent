"""
apply-agent: dedicated safe-apply subagent service.

Owns: git worktree creation, patch validation/apply, commit, push, gh draft-PR.
Called by the orchestrator (agent-api) on /confirm approval. Never exposed
to the public internet — internal-only on the compose network.

This is the fail-closed gate: unless AGENT_GIT_APPLY_ENABLED=1 this service
only validates and reports (dry_run); AGENT_GIT_DRY_RUN=1 forces validate-only
even when enabled.

Security: the repo mount is read-only for the orchestrator; this service gets
the same read-only mount plus a writable temp area for throwaway worktrees.
It never touches the orchestrator's main checkout.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Kovi Apply Agent")

ENABLED_VAR = "AGENT_GIT_APPLY_ENABLED"
REPO_VAR = "AGENT_GIT_REPO"
REMOTE_VAR = "AGENT_GIT_REMOTE"
DRY_RUN_VAR = "AGENT_GIT_DRY_RUN"
GH_BIN_VAR = "AGENT_GH_BIN"
REPO_PATH = os.environ.get("REPOS_PATH", "/repos/kovanica-protocol")

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9-]+")


@dataclass
class ApplyResult:
    status: str  # "ok" | "dry_run" | "error"
    branch: str = ""
    commit: str = ""
    pr_url: str = ""
    detail: str = ""
    applied_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "branch": self.branch,
            "commit": self.commit,
            "pr_url": self.pr_url,
            "detail": self.detail,
            "applied_files": self.applied_files,
        }


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _sanitize(text: str) -> str:
    return _SANITIZE_RE.sub("-", text).strip("-")


def _branch_name(session_id: str) -> str:
    s = _sanitize(session_id) or "session"
    short = uuid.uuid4().hex[:8]
    return f"agent/{s}-{short}"


def _safe_path(path: str) -> Path | None:
    if not path or not isinstance(path, str):
        return None
    p = Path(path)
    if p.is_absolute():
        return None
    parts = p.parts
    if not parts:
        return None
    if any(part in ("..", ".git", "") for part in parts):
        return None
    if ".git" in parts:
        return None
    if p.name in ("", ".", ".."):
        return None
    return p


def _worktree_add(repo: str, remote: str, base: str, branch: str) -> str:
    tmp = tempfile.mkdtemp(prefix="kovanica-apply-")
    worktree = str(Path(tmp) / "wt")
    subprocess.run(
        ["git", "-C", repo, "worktree", "add", worktree, "-b", branch, f"{remote}/{base}"],
        check=True, capture_output=True, text=True,
    )
    return worktree


def _worktree_remove(repo: str, worktree: str | None) -> None:
    if not worktree:
        return
    try:
        subprocess.run(
            ["git", "-C", repo, "worktree", "remove", "--force", worktree],
            capture_output=True, text=True,
        )
    except Exception:
        pass
    try:
        shutil.rmtree(Path(worktree).parent, ignore_errors=True)
    except Exception:
        pass


def _resolve_repo() -> str:
    repo = _env(REPO_VAR).strip()
    if repo:
        return repo
    cwd = Path.cwd()
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class Proposal(BaseModel):
    path: str
    explanation: str = ""
    patch: str = ""


class ApplyRequest(BaseModel):
    session_id: str
    proposals: list[Proposal]
    base: str = "main"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    return {"status": "ok", "name": "apply-agent"}


@app.get("/readyz")
def readyz():
    repo = _resolve_repo()
    has_git = False
    if repo:
        p = Path(repo)
        has_git = p.is_dir() and (p / ".git").exists()
    gh_bin = _env(GH_BIN_VAR, "gh").strip() or "gh"
    gh_ok = False
    try:
        subprocess.run([gh_bin, "auth", "status"], capture_output=True, text=True, timeout=5)
        gh_ok = True
    except Exception:
        gh_ok = False
    return {
        "status": "ok",
        "name": "apply-agent",
        "deps": {
            "repo": repo or "unset",
            "repo_git": "ok" if has_git else ("unset" if not repo else "missing"),
            "gh": "ok" if gh_ok else "unavailable",
            "apply_enabled": _env(ENABLED_VAR).strip() == "1",
        },
    }


@app.post("/apply", summary="Validate and apply proposals (dry_run unless enabled)")
def apply(req: ApplyRequest):
    enabled = _env(ENABLED_VAR).strip() == "1"
    dry_run = _env(DRY_RUN_VAR).strip() == "1" or not enabled
    repo = _resolve_repo()
    remote = _env(REMOTE_VAR, "origin").strip() or "origin"
    gh_bin = _env(GH_BIN_VAR, "gh").strip() or "gh"
    base = req.base.strip() or "main"
    branch = _branch_name(req.session_id)

    if not req.proposals:
        return ApplyResult(
            status="error", branch=branch, detail="no proposals to apply",
        ).to_dict()

    # ---- Validate all proposals up front (pure, no fs/network) --------- #
    validated: list[tuple[str, str]] = []
    for i, p in enumerate(req.proposals):
        if not p.path or not str(p.path).strip():
            return ApplyResult(
                status="error", branch=branch,
                detail=f"proposal {i}: missing path",
            ).to_dict()
        rel = _safe_path(str(p.path))
        if rel is None:
            return ApplyResult(
                status="error", branch=branch,
                detail=f"proposal {i}: unsafe path rejected: {p.path!r}",
            ).to_dict()
        if not p.patch or not str(p.patch).strip():
            return ApplyResult(
                status="error", branch=branch,
                detail=f"proposal {i}: missing patch for {p.path!r}",
            ).to_dict()
        validated.append((str(rel), str(p.patch)))

    applied_files = [rel for rel, _ in validated]

    if not enabled:
        return ApplyResult(
            status="dry_run", branch=branch,
            detail=f"apply disabled: set {ENABLED_VAR}=1 to enable real PR creation",
            applied_files=applied_files,
        ).to_dict()

    if not repo:
        return ApplyResult(
            status="error", branch=branch,
            detail="could not determine the git checkout (AGENT_GIT_REPO unset and git detection failed)",
        ).to_dict()

    repo_path = Path(repo)
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return ApplyResult(
            status="error", branch=branch,
            detail=f"repo path is not a valid git checkout: {repo}",
        ).to_dict()

    worktree = None
    try:
        subprocess.run(
            ["git", "-C", repo, "fetch", remote, base],
            check=True, capture_output=True, text=True,
        )
        worktree = _worktree_add(repo, remote, base, branch)

        root_res = subprocess.run(
            ["git", "-C", worktree, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if root_res.returncode != 0:
            raise RuntimeError("could not resolve worktree root")
        wt_root = Path(root_res.stdout.strip()).resolve()

        for rel, patch in validated:
            target = (wt_root / rel).resolve()
            try:
                target.relative_to(wt_root)
            except ValueError:
                raise RuntimeError(f"resolved target escapes worktree: {target!r}")
            check = subprocess.run(
                ["git", "-C", worktree, "apply", "--check", "-"],
                input=patch, capture_output=True, text=True,
            )
            if check.returncode != 0:
                detail = (check.stderr or check.stdout or "git apply --check failed").strip()
                raise RuntimeError(f"patch check failed for {rel}: {detail}")
            result = subprocess.run(
                ["git", "-C", worktree, "apply", "-"],
                input=patch, capture_output=True, text=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "git apply failed").strip()
                raise RuntimeError(f"apply failed for {rel}: {detail}")

        if dry_run:
            return ApplyResult(
                status="dry_run", branch=branch,
                detail="dry-run: patches would be applied; commit/push/PR skipped",
                applied_files=applied_files,
            ).to_dict()

        # ---- Commit ------------------------------------------------ #
        first_explanation = req.proposals[0].explanation or ""
        subject = first_explanation.strip().splitlines()[0].strip() if first_explanation.strip() else ""
        if not subject:
            subject = "feat(agent): apply proposed patch"
        body_lines = []
        for p in req.proposals:
            expl = p.explanation or ""
            if expl.strip():
                body_lines.append(expl.strip())
        message = subject
        if body_lines:
            message += "\n\n" + "\n\n".join(body_lines)

        subprocess.run(["git", "-C", worktree, "add", "-A"], check=True, capture_output=True, text=True)
        commit_res = subprocess.run(
            ["git", "-C", worktree, "commit", "-m", message],
            capture_output=True, text=True,
        )
        if commit_res.returncode != 0:
            detail = (commit_res.stderr or commit_res.stdout or "git commit failed").strip()
            raise RuntimeError(f"commit failed: {detail}")
        commit_hash = subprocess.run(
            ["git", "-C", worktree, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        # ---- Push + open draft PR -------------------------------- #
        push = subprocess.run(
            ["git", "-C", worktree, "push", "-u", remote, branch],
            capture_output=True, text=True,
        )
        if push.returncode != 0:
            raise RuntimeError("push failed: " + (push.stderr or push.stdout).strip())

        pr_body = "\n\n".join(
            f"**{(p.explanation or '(no explanation)').strip()}**" for p in req.proposals
        )
        gh = subprocess.run(
            [gh_bin, "pr", "create", "--draft",
             "--base", base, "--head", branch,
             "--title", subject, "--body", pr_body],
            capture_output=True, text=True,
        )
        if gh.returncode != 0:
            detail = (gh.stderr or gh.stdout or "gh pr create failed").strip()
            raise RuntimeError(f"gh pr create failed: {detail}")

        pr_url = ""
        for line in (gh.stdout + "\n" + gh.stderr).splitlines():
            line = line.strip()
            if line.startswith("https://"):
                pr_url = line
                break

        return ApplyResult(
            status="ok", branch=branch, commit=commit_hash, pr_url=pr_url,
            detail="applied, committed, pushed, and draft PR opened",
            applied_files=applied_files,
        ).to_dict()

    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        return ApplyResult(
            status="error", branch=branch, detail=detail or "git operation failed",
            applied_files=applied_files,
        ).to_dict()
    except RuntimeError as e:
        return ApplyResult(
            status="error", branch=branch, detail=str(e),
            applied_files=applied_files,
        ).to_dict()
    except Exception as e:
        return ApplyResult(
            status="error", branch=branch,
            detail=f"unexpected error: {e}",
            applied_files=applied_files,
        ).to_dict()
    finally:
        _worktree_remove(repo, worktree)
