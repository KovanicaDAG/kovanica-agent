"""
Kovanica cloud agent delegation — push/pull handoff via agent-api (KovanicaClient).
Mirrors Codex cloud agent delegation.
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    from kovanica_sdk import KovanicaClient
except ImportError:
    KovanicaClient = None


def _get_client() -> KovanicaClient | None:
    if KovanicaClient is None:
        return None
    api_url = os.environ.get("KOVANICA_API_URL", "") or ""
    if not api_url:
        return None
    token = os.environ.get("KOVANICA_API_TOKEN", "") or None
    timeout = int(os.environ.get("KOVANICA_CHAT_TIMEOUT", "900") or 900)
    return KovanicaClient(
        base_url=api_url,
        token=token,
        search_agent_url=os.environ.get("SEARCH_AGENT_URL", ""),
        apply_agent_url=os.environ.get("APPLY_AGENT_URL", ""),
        timeout=timeout,
    )


def cloud_push(session_id: str, message: str, model: str | None = None) -> dict[str, Any]:
    """Push a conversation turn to a remote agent-api for async/cloud processing."""
    client = _get_client()
    if client is None:
        return {"status": "error", "detail": "KOVI_API_URL not set — cannot push to cloud"}
    try:
        # Mirror the chat API: push message, get reply back
        result = client.chat(session_id, message)
        reply = getattr(result, "reply", None) or getattr(result, "detail", None) or ""
        return {
            "status": "pushed",
            "session_id": session_id,
            "reply_preview": reply[:500] if reply else None,
            "detail": "cloud turn pushed successfully",
        }
    except Exception as exc:
        return {"status": "error", "detail": f"cloud push failed: {exc}"}


def cloud_pull(session_id: str) -> dict[str, Any]:
    """Pull the latest result for a session from the remote agent-api."""
    client = _get_client()
    if client is None:
        return {"status": "error", "detail": "KOVI_API_URL not set — cannot pull from cloud"}
    try:
        result = client.chat(session_id, "[cloud-pull]")
        reply = getattr(result, "reply", None) or getattr(result, "detail", None) or ""
        return {
            "status": "ok" if reply else "pending",
            "session_id": session_id,
            "reply": reply,
        }
    except Exception as exc:
        return {"status": "error", "detail": f"cloud pull failed: {exc}"}


def cloud_status(session_id: str) -> dict[str, Any]:
    """Check the status of a cloud job for a session."""
    client = _get_client()
    if client is None:
        return {"status": "error", "detail": "KOVI_API_URL not set"}
    try:
        data = client.healthz()
        return {
            "status": "ok" if data.get("status") == "ok" else "unhealthy",
            "session_id": session_id,
            "agent_api": data,
        }
    except Exception as exc:
        return {"status": "error", "detail": f"cloud status check failed: {exc}"}
