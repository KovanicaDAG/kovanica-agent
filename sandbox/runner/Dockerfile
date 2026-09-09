# sandbox-runner sidecar — the ONLY service that mounts the Docker socket.
# agent-api talks to this over HTTP (SANDBOX_RUNNER_URL) instead of touching
# /var/run/docker.sock directly, so a compromised agent-api can never drive
# arbitrary containers — it can only ask this sidecar to run one whitelisted
# cargo command against the shared repo mount.
#
# It needs the socket (mounted at compose time) but is otherwise kept minimal:
# read-only rootfs, non-root user, and a tmpfs on /tmp.
FROM python:3.12-slim

RUN useradd -r -u 10001 sandbox-runner

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

USER sandbox-runner

EXPOSE 8081
CMD ["python", "-u", "server.py"]
