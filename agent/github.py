"""
Kovanica GitHub PR review flow — gh CLI integration for PR review and creation.

Mirrors Claude Code / Codex's GitHub integration:
- PR review (comments, approvals)
- PR creation
- PR listing
"""

from __future__ import annotations

import subprocess
import json as _json
from typing import Any

def _gh_available() -> bool:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def gh_pr_review(pr_number: int, comments: list[str]) -> dict[str, Any]:
    if not _gh_available():
        return {"error": "gh CLI not available or not authenticated"}
    try:
        for comment in comments:
            result = subprocess.run(
                ["gh", "pr", "comment", str(pr_number), "--body", comment],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                return {"error": f"gh pr comment failed: {result.stderr[:300]}"}
        return {"status": "ok", "pr": pr_number, "comments_posted": len(comments)}
    except subprocess.TimeoutExpired:
        return {"error": "gh pr review timed out"}
    except Exception as exc:
        return {"error": f"gh pr review failed: {exc}"}

def gh_pr_create(title: str, body: str, head: str, base: str = "main") -> dict[str, Any]:
    if not _gh_available():
        return {"error": "gh CLI not available or not authenticated"}
    try:
        result = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body, "--head", head, "--base", base],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            return {"status": "ok", "pr_url": pr_url}
        return {"error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "gh pr create timed out"}
    except Exception as exc:
        return {"error": f"gh pr create failed: {exc}"}

def gh_pr_list(state: str = "open") -> list[dict[str, Any]]:
    if not _gh_available():
        return []
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--json", "number,title,url,author,state"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return _json.loads(result.stdout)
        return []
    except Exception:
        return []

def gh_pr_view(pr_number: int) -> dict[str, Any]:
    if not _gh_available():
        return {"error": "gh CLI not available"}
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "number,title,url,state,author,reviews"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return _json.loads(result.stdout)
        return {"error": result.stderr[:300]}
    except Exception as exc:
        return {"error": f"gh pr view failed: {exc}"}
