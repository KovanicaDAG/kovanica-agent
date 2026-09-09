"""
sandbox_client — the agent-side client for the sandbox-runner sidecar.

The agent (graph.py) no longer touches the Docker socket directly. Instead it
POSTs a single whitelisted cargo command to the sandbox-runner sidecar, which
is the ONLY service allowed to spawn sandbox containers. This module hides the
HTTP plumbing and normalises the result into a readable string.

graph.py's run_cargo_command should delegate here, e.g.::

    from sandbox_client import run_cargo
    return run_cargo(command, args, repo_path)

`repo_path` is interpreted *in the sidecar's filesystem* — it must be the path
of the shared read-only repo mount as the sidecar sees it (default /repos).
"""

import os

import requests

SANDBOX_RUNNER_URL = os.environ.get(
    "SANDBOX_RUNNER_URL", "http://sandbox-runner:8081"
).rstrip("/")
RUN_ENDPOINT = f"{SANDBOX_RUNNER_URL}/run"
DEFAULT_REPO_PATH = os.environ.get("REPOS_PATH", "/repos")
DEFAULT_TIMEOUT_S = 180
# The sidecar caps at MAX_TIMEOUT_S; keep a little headroom for the HTTP call.
HTTP_TIMEOUT_S = 600


def run_cargo(
    command: str,
    args: list[str] | None = None,
    repo_path: str = DEFAULT_REPO_PATH,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Ask the sandbox-runner sidecar to run one whitelisted cargo command.

    Returns a readable result string — the command's combined output on
    success, or the runner's structured error / a connection message. Callers
    should treat the string as opaque (the agent will surface it to the LLM).
    """
    payload = {
        "command": command,
        "args": list(args or []),
        "repo_path": repo_path,
        "timeout_s": timeout_s,
    }
    try:
        resp = requests.post(RUN_ENDPOINT, json=payload, timeout=HTTP_TIMEOUT_S)
    except requests.exceptions.ConnectionError as e:
        return (
            f"ERROR: cannot reach sandbox-runner at {SANDBOX_RUNNER_URL} "
            f"(connection refused): {e}"
        )
    except requests.exceptions.Timeout as e:
        return (
            f"ERROR: sandbox-runner at {SANDBOX_RUNNER_URL} timed out "
            f"after {HTTP_TIMEOUT_S}s: {e}"
        )
    except requests.exceptions.RequestException as e:
        return f"ERROR: sandbox-runner request failed: {e}"

    try:
        result = resp.json()
    except ValueError:
        return (
            f"ERROR: sandbox-runner returned non-JSON HTTP {resp.status_code}: "
            f"{resp.text!r}"
        )

    body = result.get("body", "")
    status = result.get("status", "")

    if status == "ok" and resp.status_code == 200:
        return body or ""

    if status == "rejected":
        return f"REJECTED: {body}"

    if status == "failed":
        return body

    return f"ERROR (HTTP {resp.status_code}): {body}"
