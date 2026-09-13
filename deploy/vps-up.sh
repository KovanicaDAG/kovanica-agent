#!/usr/bin/env bash
# Bring Kovanica up on the Kovanica VPS (CPU compose) and point
# kovanica.kovanica.online at it. Idempotent: safe to re-run after a git pull.
#
# Expected layout on srv1745734:
#   /root/kovanica-protocol          protocol checkout (already there)
#   this script lives in             kovanica-agent/deploy/vps-up.sh
#                                    (nested in the protocol tree, or a
#                                    standalone /root/kovanica-agent)
set -euo pipefail

AGENT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROTOCOL_ROOT="${KOVANICA_PROTOCOL_ROOT:-/root/kovanica-protocol}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.cpu.yml)

echo "==> Kovanica deploy from $AGENT_ROOT"

if [[ ! -f "$PROTOCOL_ROOT/Cargo.toml" ]]; then
  echo "error: protocol checkout not found at $PROTOCOL_ROOT" >&2
  exit 1
fi

mkdir -p "$AGENT_ROOT/repos"
ln -sfn "$PROTOCOL_ROOT" "$AGENT_ROOT/repos/kovanica-protocol"

if [[ ! -f "$AGENT_ROOT/.env" ]]; then
  echo "==> writing $AGENT_ROOT/.env"
  umask 077
  docker_gid="$(stat -c %g /var/run/docker.sock 2>/dev/null || echo 988)"
  cat > "$AGENT_ROOT/.env" <<EOF
AUTH_DEV_TOKEN=$(openssl rand -hex 24)
DOCKER_GID=$docker_gid
SANDBOX_RUNNER_TOKEN=$(openssl rand -hex 16)
CORS_ORIGINS=https://kovanica.kovanica.online,https://kovanica.online,https://www.kovanica.online
KOVANICA_NODE_URL=https://explorer.kovanica.online
AGENT_GIT_DRY_RUN=1
AGENT_MODEL=qwen2.5-coder:3b
EOF
else
  echo "==> keeping existing $AGENT_ROOT/.env"
fi

# Export DOCKER_GID for compose group_add even if .env is older.
if ! grep -q '^DOCKER_GID=' "$AGENT_ROOT/.env"; then
  echo "DOCKER_GID=$(stat -c %g /var/run/docker.sock 2>/dev/null || echo 988)" >> "$AGENT_ROOT/.env"
fi
set -a
# shellcheck disable=SC1091
source "$AGENT_ROOT/.env"
set +a
export DOCKER_GID="${DOCKER_GID:-$(stat -c %g /var/run/docker.sock 2>/dev/null || echo 988)}"

echo "==> nginx vhost kovanica.kovanica.online (HTTP + HTTPS)"
if [[ -d /etc/nginx/sites-available ]]; then
  # If kovanica was added as a server_name on the website vhost, SNI steals
  # requests. Strip it from every other site before installing ours.
  for f in /etc/nginx/sites-available/* /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*; do
    [[ -e "$f" ]] || continue
    base="$(basename "$f")"
    [[ "$base" == "kovanica.kovanica.online" ]] && continue
    if grep -q 'kovanica\.kovanica\.online' "$f" 2>/dev/null; then
      echo "    stripping kovanica.kovanica.online from $f"
      sed -i -E 's/[[:space:]]*kovanica\.kovanica\.online//g' "$f"
    fi
  done

  cert=""
  key=""
  for d in /etc/letsencrypt/live/kovanica.kovanica.online \
           /etc/letsencrypt/live/kovanica.online \
           /etc/letsencrypt/live/explorer.kovanica.online; do
    if [[ -f "$d/fullchain.pem" && -f "$d/privkey.pem" ]]; then
      cert="$d/fullchain.pem"
      key="$d/privkey.pem"
      echo "    using cert $d"
      break
    fi
  done
  if [[ -z "$cert" ]]; then
    echo "error: no TLS cert found under /etc/letsencrypt/live for kovanica" >&2
    ls -la /etc/letsencrypt/live || true
    exit 1
  fi

  sed -e "s|__SSL_CERT__|$cert|g" -e "s|__SSL_KEY__|$key|g" \
    "$AGENT_ROOT/deploy/nginx-kovi.conf" \
    > /etc/nginx/sites-available/kovanica.kovanica.online
  ln -sfn /etc/nginx/sites-available/kovanica.kovanica.online \
    /etc/nginx/sites-enabled/kovanica.kovanica.online
  nginx -t
  systemctl reload nginx
else
  echo "warn: nginx sites-available missing; skip vhost" >&2
fi

echo "==> stopping previous agent compose (so ports can re-bind loopback)"
for dir in "$AGENT_ROOT" /root/kovanica-agent; do
  if [[ -f "$dir/docker-compose.yml" ]]; then
    docker compose -f "$dir/docker-compose.yml" -f "$dir/docker-compose.cpu.yml" \
      down --remove-orphans >/dev/null 2>&1 || true
  fi
done

echo "==> docker compose build + up (qdrant, ollama/vllm, sandbox-runner, agent-api)"
cd "$AGENT_ROOT"
"${COMPOSE[@]}" build agent-api sandbox-runner
"${COMPOSE[@]}" up -d --force-recreate qdrant vllm sandbox-runner agent-api

echo "==> waiting for Ollama"
ok=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T vllm ollama list >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "$ok" -ne 1 ]]; then
  echo "error: ollama did not become ready" >&2
  "${COMPOSE[@]}" logs --tail=80 vllm || true
  exit 1
fi

echo "==> pulling qwen2.5-coder:3b (no-op if already present)"
"${COMPOSE[@]}" exec -T vllm ollama pull qwen2.5-coder:3b

echo "==> waiting for agent-api /healthz"
ok=0
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:13080/healthz >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "$ok" -ne 1 ]]; then
  echo "error: agent-api did not become ready on :13080" >&2
  "${COMPOSE[@]}" logs --tail=80 agent-api || true
  exit 1
fi

echo "==> index protocol repo if the collection is empty"
if ! "${COMPOSE[@]}" exec -T agent-api python - <<'PY'
from qdrant_client import QdrantClient
import os, sys
c = QdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"))
names = {x.name for x in c.get_collections().collections}
sys.exit(0 if "kovanica_codebase" in names else 1)
PY
then
  echo "    first index (this takes a few minutes)…"
  "${COMPOSE[@]}" exec -T agent-api python -m indexer --repo /repos/kovanica-protocol
else
  echo "    collection already present — skip (pass --recreate manually to rebuild)"
fi

echo "==> Kovanica is up"
curl -fsS http://127.0.0.1:13080/healthz
echo
echo "Public: https://kovanica.kovanica.online"
echo "Local:  http://127.0.0.1:13080"
