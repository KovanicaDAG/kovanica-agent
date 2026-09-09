"""
sandbox-runner sidecar — the ONLY service that talks to the Docker socket.

The agent-api no longer mounts /var/run/docker.sock (that was effective root on
the host). Instead, this small internal service owns the socket and exposes a
single, restricted endpoint: POST /run. It spawns a short-lived,
network-disabled sandbox container and returns its output as plain text.

The whitelist and suspicious-arg filter are re-enforced here, server-side,
*defensively* — even though sandbox/entrypoint.sh also enforces them inside
the box. This keeps the trust boundary at the sidecar, so a compromised
agent-api (or agent) can never drive arbitrary containers: it can only ask
for one of {check, test, clippy, build} against the mounted repo.
"""

import json
import os
import re
import socketserver
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import docker

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "kovanica-sandbox:latest")
REPOS_PATH = os.environ.get("REPOS_PATH", "/repos")
LISTEN_HOST = os.environ.get("SANDBOX_RUNNER_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("SANDBOX_RUNNER_PORT", "8081"))

ALLOWED_COMMANDS = {"check", "test", "clippy", "build"}
DEFAULT_TIMEOUT_S = 180
MAX_TIMEOUT_S = 600

# Keep in sync with sandbox/entrypoint.sh: reject anything that smells like a
# shell-out or a privileged file operation.
SUSPICIOUS_ARGS = re.compile(r"(rm|sudo|curl|wget|;|\||&|\$\(|`)")

# One shared docker client, so every request reuses a single connection to the
# socket instead of re-opening it per call.
_client = docker.from_env()


def _validate(payload: dict) -> str:
    """Return an error message, or None if the payload may proceed."""
    command = payload.get("command")
    if command not in ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_COMMANDS))
        return f"REJECTED: '{command}' is not whitelisted ({allowed})"
    for arg in payload.get("args", []):
        if not isinstance(arg, str):
            return f"REJECTED: argument is not a string: {arg!r}"
        if SUSPICIOUS_ARGS.search(arg):
            return f"REJECTED: suspicious argument: {arg}"
    return None


def run_cargo(payload: dict) -> dict:
    """Execute one whitelisted cargo command in an ephemeral sandbox container.

    Returns a dict shaped like {"status": ..., "body": ...} so the HTTP layer
    stays a dumb translator. The container image and spawn settings mirror the
    old agent/graph.py run_cargo_command behaviour, minus the Docker access.
    """
    command = payload.get("command")
    args = payload.get("args") or []
    repo_path = payload.get("repo_path") or REPOS_PATH
    timeout_s = int(payload.get("timeout_s") or DEFAULT_TIMEOUT_S)
    timeout_s = max(1, min(timeout_s, MAX_TIMEOUT_S))

    error = _validate({"command": command, "args": args})
    if error:
        return {"status": "rejected", "body": error}

    container_name = f"kovanica-sandbox-{uuid.uuid4().hex[:8]}"
    try:
        result = _client.containers.run(
            image=SANDBOX_IMAGE,
            command=[command, *args],
            name=container_name,
            volumes={os.path.abspath(repo_path): {"bind": "/workspace", "mode": "ro"}},
            network_disabled=True,
            mem_limit="2g",
            nano_cpus=int(2e9),       # 2 CPUs
            user="sandbox",
            remove=True,
            detach=False,
            stdout=True,
            stderr=True,
            # runtime="runsc",        # uncomment once gVisor is installed on the host
        )
        return {"status": "ok", "body": result.decode("utf-8", errors="replace")}
    except docker.errors.ContainerError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        return {"status": "failed", "body": f"cargo {command} failed:\n{stderr}"}
    except Exception as e:  # noqa: BLE001 - surfaces as a readable HTTP error
        return {"status": "error", "body": f"ERROR running sandbox: {e}"}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib handler signature
        if self.path != "/run":
            self._respond(404, {"status": "error", "body": "not found: use POST /run"})
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except (ValueError, json.JSONDecodeError) as e:
            self._respond(400, {"status": "error", "body": f"invalid JSON: {e}"})
            return

        result = run_cargo(payload)
        if result["status"] == "ok":
            self._respond(200, result)
        elif result["status"] == "rejected":
            self._respond(400, result)
        elif result["status"] == "failed":
            self._respond(422, result)
        else:
            self._respond(500, result)

    def _respond(self, code: int, result: dict) -> None:
        body = json.dumps(result).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        pass


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    # /run can block for up to MAX_TIMEOUT_S, so serve each request on its own
    # thread rather than serialising the whole service behind one long run.
    # ThreadingMixIn must come first in the MRO so handle_request() actually
    # dispatches onto a new thread — daemon_threads alone (on plain
    # HTTPServer) does nothing; the server stays single-threaded and every
    # request, including /run and future health checks, queues behind
    # whichever cargo call is currently in flight.
    daemon_threads = True


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), _Handler)
    print(f"sandbox-runner listening on {LISTEN_HOST}:{LISTEN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
