"""Safe application of approved proposals to a throwaway git worktree.

Orchestrates: validate -> create throwaway worktree/branch -> apply patches ->
(commit / push / open DRAFT PR only if enabled) -> cleanup. Security-sensitive:
never mutates the user's main checkout, and any real git/network mutation is
FAIL-CLOSED behind ``AGENT_GIT_APPLY_ENABLED == "1"``.
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

__all__ = ["ApplyResult", "apply_and_open_pr"]

ENABLED_VAR = "AGENT_GIT_APPLY_ENABLED"
REPO_VAR = "AGENT_GIT_REPO"
REMOTE_VAR = "AGENT_GIT_REMOTE"
DRY_RUN_VAR = "AGENT_GIT_DRY_RUN"
GH_BIN_VAR = "AGENT_GH_BIN"

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9-]+")


@dataclass
class ApplyResult:
    """Outcome of applying proposals.

    status
        ``"ok"``  — successfully applied (committed, pushed, PR opened).
        ``"dry_run"`` — validated, but nothing was created on disk/network.
        ``"error"``  — validation/apply failed; nothing was changed.
    branch
        Generated branch name (present even in dry-run/error where derivable).
    commit
        Commit hash when a commit was actually created.
    pr_url
        URL of the opened draft PR, when one was opened.
    detail
        Human-readable detail / error message.
    applied_files
        Repo-relative paths of proposals that passed validation (in dry-run),
        or that were successfully applied.
    """

    status: str
    branch: str = ""
    commit: str = ""
    pr_url: str = ""
    detail: str = ""
    applied_files: list[str] = field(default_factory=list)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _sanitize_branch_component(text: str) -> str:
    return _SANITIZE_RE.sub("-", text).strip("-")


def _resolve_base_ref() -> str:
    """Return the main checkout path: env override, else git-detected, else empty."""
    repo = _env(REPO_VAR).strip()
    if repo:
        return repo
    cwd = Path.cwd()
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.strip()


def _safe_path(path: str) -> Path | None:
    """Validate a proposal path. Return a relative Path, or None if unsafe."""
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


def _build_branch_name(session_id: str) -> str:
    session = _sanitize_branch_component(session_id) or "session"
    short = uuid.uuid4().hex[:8]
    return f"agent/{session}-{short}"


def _worktree_add(repo: str, remote: str, base: str, branch: str) -> str:
    """Create a throwaway worktree checked out from remote/base. Return the dir."""
    tmp = tempfile.mkdtemp(prefix="kovanica-apply-")
    worktree = str(Path(tmp) / "wt")
    subprocess.run(
        ["git", "-C", repo, "worktree", "add", worktree, "-b", branch, f"{remote}/{base}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return worktree


def _worktree_remove(repo: str, worktree: str | None) -> None:
    """Safely tear down a worktree (best-effort)."""
    if not worktree:
        return
    try:
        subprocess.run(
            ["git", "-C", repo, "worktree", "remove", "--force", worktree],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass
    try:
        shutil.rmtree(Path(worktree).parent, ignore_errors=True)
    except Exception:
        pass


def apply_and_open_pr(
    session_id: str,
    proposals,
    *,
    base: str = "main",
    dry_run: bool = True,
) -> ApplyResult:
    """Validate and apply proposals; optionally commit/push/open a draft PR.

    Env-gated and fail-closed: unless ``AGENT_GIT_APPLY_ENABLED == "1"`` this
    function validates only and never touches the filesystem or network.
    """
    enabled = _env(ENABLED_VAR).strip() == "1"
    repo = _resolve_base_ref()
    remote = _env(REMOTE_VAR, "origin").strip() or "origin"
    gh_bin = _env(GH_BIN_VAR, "gh").strip() or "gh"

    if _env(DRY_RUN_VAR).strip() == "1":
        dry_run = True

    branch = _build_branch_name(session_id)
    worktree: str | None = None

    applied_files: list[str] = []
    validated: list[tuple[str, str]] = []

    if not proposals:
        return ApplyResult(
            status="error",
            branch=branch,
            detail="no proposals to apply",
        )

    # ---- Validate all proposals up front (pure, no fs/network) ---------
    for i, p in enumerate(proposals):
        path = getattr(p, "path", None)
        patch = getattr(p, "patch", None)
        if not path or not str(path).strip():
            return ApplyResult(
                status="error",
                branch=branch,
                detail=f"proposal {i}: missing path",
            )
        rel = _safe_path(str(path))
        if rel is None:
            return ApplyResult(
                status="error",
                branch=branch,
                detail=f"proposal {i}: unsafe path rejected: {path!r}",
            )
        if not patch or not str(patch).strip():
            return ApplyResult(
                status="error",
                branch=branch,
                detail=f"proposal {i}: missing patch for {path!r}",
            )
        validated.append((str(rel), str(patch)))

    applied_files = [rel for rel, _ in validated]

    # Every proposal validated cleanly. If apply is disabled, stop here —
    # never touch the filesystem or network.
    if not enabled:
        return ApplyResult(
            status="dry_run",
            branch=branch,
            detail=(
                f"apply disabled: set {ENABLED_VAR}=1 to enable real PR creation"
            ),
            applied_files=applied_files,
        )

    if not repo:
        return ApplyResult(
            status="error",
            branch=branch,
            detail="could not determine the git checkout (AGENT_GIT_REPO unset and git detection failed)",
        )

    repo_path = Path(repo)
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return ApplyResult(
            status="error",
            branch=branch,
            detail=f"repo path is not a valid git checkout: {repo}",
        )

    try:
        # Fetch/ensure the remote ref is available.
        subprocess.run(
            ["git", "-C", repo, "fetch", remote, base],
            check=True,
            capture_output=True,
            text=True,
        )

        # Create throwaway worktree/branch based on remote.
        worktree = _worktree_add(repo, remote, base, branch)

        # Resolve the worktree's repo root for containment checks.
        root_res = subprocess.run(
            ["git", "-C", worktree, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if root_res.returncode != 0:
            raise RuntimeError("could not resolve worktree root")
        wt_root = Path(root_res.stdout.strip()).resolve()

        # ---- Apply patches one at a time, --check first ----------------
        for rel, patch in validated:
            target = (wt_root / rel).resolve()
            try:
                target.relative_to(wt_root)
            except ValueError:
                raise RuntimeError(
                    f"resolved target escapes worktree: {target!r}"
                )

            check = subprocess.run(
                ["git", "-C", worktree, "apply", "--check", "-"],
                input=patch,
                capture_output=True,
                text=True,
            )
            if check.returncode != 0:
                detail = (check.stderr or check.stdout or "git apply --check failed").strip()
                raise RuntimeError(f"patch check failed for {rel}: {detail}")

            result = subprocess.run(
                ["git", "-C", worktree, "apply", "-"],
                input=patch,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "git apply failed").strip()
                raise RuntimeError(f"apply failed for {rel}: {detail}")

        if dry_run:
            return ApplyResult(
                status="dry_run",
                branch=branch,
                detail="dry-run: patches would be applied; commit/push/PR skipped",
                applied_files=applied_files,
            )

        # ---- Commit ----------------------------------------------------
        first_explanation = getattr(proposals[0], "explanation", "") or ""
        subject = first_explanation.strip().splitlines()[0].strip() if first_explanation.strip() else ""
        if not subject:
            subject = "feat(agent): apply proposed patch"
        body_lines = []
        for p in proposals:
            expl = (getattr(p, "explanation", "") or "").strip()
            if expl:
                body_lines.append(expl)
        message = subject
        if body_lines:
            message += "\n\n" + "\n\n".join(body_lines)

        subprocess.run(["git", "-C", worktree, "add", "-A"], check=True, capture_output=True, text=True)

        commit_res = subprocess.run(
            ["git", "-C", worktree, "commit", "-m", message],
            capture_output=True,
            text=True,
        )
        if commit_res.returncode != 0:
            detail = (commit_res.stderr or commit_res.stdout or "git commit failed").strip()
            raise RuntimeError(f"commit failed: {detail}")
        commit_hash = subprocess.run(
            ["git", "-C", worktree, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        # ---- Push + open draft PR --------------------------------------
        push = subprocess.run(
            ["git", "-C", worktree, "push", "-u", remote, branch],
            capture_output=True,
            text=True,
        )
        if push.returncode != 0:
            raise RuntimeError("push failed: " + (push.stderr or push.stdout).strip())

        pr_body = "\n\n".join(
            f"**{getattr(p, 'explanation', '') or '(no explanation)'}**" for p in proposals
        )
        gh = subprocess.run(
            [gh_bin, "pr", "create", "--draft",
             "--base", base,
             "--head", branch,
             "--title", subject,
             "--body", pr_body],
            capture_output=True,
            text=True,
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
            status="ok",
            branch=branch,
            commit=commit_hash,
            pr_url=pr_url,
            detail="applied, committed, pushed, and draft PR opened",
            applied_files=applied_files,
        )

    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or str(e)).strip()
        return ApplyResult(
            status="error",
            branch=branch,
            detail=detail or "git operation failed",
            applied_files=applied_files,
        )
    except RuntimeError as e:
        return ApplyResult(
            status="error",
            branch=branch,
            detail=str(e),
            applied_files=applied_files,
        )
    except Exception as e:  # noqa: BLE001 - defensive catch-all
        return ApplyResult(
            status="error",
            branch=branch,
            detail=f"unexpected error: {e}",
            applied_files=applied_files,
        )
    finally:
        _worktree_remove(repo, worktree)
