# Kovi — Kovanica Engineering Agent

> **Kovi, Product of Kovanica.** A RAG-powered engineering agent for the
> kovanica-protocol codebase: FastAPI `/chat` + `/confirm`, LangGraph with
> SQLite checkpoints, Qdrant/fastembed semantic codebase search, and a
> network-disabled sandbox for `cargo` runs. It can propose patches and — when
> armed — open draft PRs from `/confirm`.
>
> Public chat: **https://kovi.kovanica.online**

## Build & run

> **Standalone checkout.** If `kovanica-agent/` is checked out as its own repo
> (not inside the kovanica-protocol tree), build the sandbox image first with
> `sandbox/build-image.sh` (it needs `KOVANICA_PROTOCOL_ROOT` pointing at a
> kovanica-protocol checkout, default `../kovanica-protocol`), then run the
> stack below. Inside the protocol tree, the compose `context: ..` resolves the
> manifests automatically.

```bash
# 1. Build the sandbox image (not run as a persistent service)
docker compose --profile build-only build sandbox-image
#    standalone: KOVANICA_PROTOCOL_ROOT=/path/to/kovanica-protocol ./sandbox/build-image.sh

# 2. Build the sandbox-runner sidecar (owns the Docker socket) and the rest
docker compose up -d vllm qdrant sandbox-runner agent-api

# CPU-only host (no NVIDIA GPU): overrides vllm with Ollama on 11434,
# remaps agent-api -> 127.0.0.1:13080 (host ports busy). Public nginx
# fronts that at https://kovi.kovanica.online.
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d \
  qdrant vllm sandbox-runner agent-api

# On the VPS this is just:
#   ./deploy/vps-up.sh

# 3. Pull the model (GPU: vLLM serves Qwen/Qwen2.5-Coder-32B-Instruct-AWQ;
#    CPU: ollama pull qwen2.5-coder:3b) and index the repo once:
docker exec kovanica-agent-agent-api-1 python /app/indexer.py --repo /repos/kovanica-protocol

# 3b. Optional: also index the Kovanica Blockchain Developer skill's
#     reference docs (RFC-001..006, tokenomics, GHOSTDAG notes, node ops,
#     API shapes, mainnet checklist) into their own collection, so
#     search_kovanica_docs / explain_concept can ground on them. Mount or
#     copy the skill's `references/` dir into the container first, e.g. at
#     /skills/kovanica-blockchain-developer/references, then:
docker exec kovanica-agent-agent-api-1 python /app/indexer.py \
  --skill-docs /skills/kovanica-blockchain-developer/references
# Re-run (no --recreate needed) whenever the skill's reference docs change.
# --repo and --skill-docs can also be combined in one invocation.
```

Kovi UI:     http://localhost:13080  (GPU: :8080) — also https://kovi.kovanica.online
Agent API:   POST /chat  and  POST /confirm
Open WebUI:  operator profile only (`--profile operator`), loopback :13000 / :3000

Set `AUTH_DEV_TOKEN` in `.env` (compose reads it) — a request with
`Authorization: Bearer *** maps to the `dev` role (needed for `/confirm`).
Without it, every visitor is `user` (read-only tools). Copy `.env.example`.

## Architecture — who owns the Docker socket

The agent's `run_cargo_command` runs inside an ephemeral, network-disabled
sandbox container. **Only the `sandbox-runner` sidecar mounts
`/var/run/docker.sock`** — it is the single, least-privileged owner of all
container spawning. `agent-api` no longer mounts the socket (mounting it would
give agent-api effective root on the host) and instead POSTs a single
whitelisted cargo command to the sidecar:

```
agent-api ──POST /run──▶ sandbox-runner (owns docker.sock) ──spawn──▶ kovanica-sandbox:latest
   (sandbox_client.py)    (sandbox/runner/server.py)          network_disabled, --rm, 2g/2CPU, user=sandbox
```

- `agent-api` sets `SANDBOX_RUNNER_URL=http://sandbox-runner:8081` and calls
  `sandbox_client.run_cargo(command, args, repo_path)`
  (`agent/sandbox_client.py`).
- `sandbox-runner` (`sandbox/runner/server.py`) re-enforces the cargo whitelist
  (`check|test|clippy|build`) and the suspicious-arg filter *server-side*,
  defensively, even though `sandbox/entrypoint.sh` also enforces them inside
  the box. A compromised agent-api can therefore never drive arbitrary
  containers — only one of the four whitelisted commands against the shared
  read-only repo mount.
- The ephemeral sandbox containers themselves stay unchanged in posture:
  `network_disabled=True`, `mem_limit="2g"`, 2 CPUs, `user="sandbox"`,
  `remove=True`, and a read-only bind of the repo into `/workspace`.

`graph.py`'s `run_cargo_command` is wired to delegate to
`sandbox_client.run_cargo`.

## What's implemented (starting work shipped)

- **Public chat UI** (`agent/static/index.html` served at `GET /`): Kovanica-branded
  Kovi console at https://kovi.kovanica.online. `/chat` + `/confirm` + `/healthz`.
- **VPS deploy** (`deploy/vps-up.sh` + `deploy/nginx-kovi.conf`): CPU compose,
  loopback binds, nginx vhost, first-run Ollama pull + Qdrant index.
- **Real JWT auth** (`agent/auth.py`): JWKS mode when `AUTH_JWKS_URL` is set, or a
  dev shared-secret mode via `AUTH_DEV_TOKEN`. `role` is always derived from the
  verified token server-side; unset config = everyone is `user` (fail-closed for dev).
- **RAG codebase search** (`agent/rag.py` + `agent/indexer.py` + `agent/embed.py`):
  Rust-aware chunking (fn/impl/struct/enum/trait/mod blocks with accurate line
  numbers) + markdown/section chunking for docs, embedded via fastembed
  (`BAAI/bge-small-en-v1.5`, 384-dim) into a Qdrant `kovanica_codebase` collection.
  Index with: `python -m indexer --repo /repos/kovanica-protocol --recreate`.
- **RAG skill-docs search** (same `rag.py`/`indexer.py`, separate collection):
  the Kovanica Blockchain Developer skill's `references/*.md` (RFCs,
  tokenomics, GHOSTDAG notes, node ops, API shapes) indexed into
  `kovanica_skill_docs` with payload `source=skill_doc`, kept out of the
  code collection so citations never conflate a reference doc with a real
  repo path. Exposed via the `search_kovanica_docs` tool (both dev and user
  roles) and folded into `explain_concept` and the CPU-model grounding
  fallback. Index with:
  `python -m indexer --skill-docs /path/to/references --recreate`.

- **Read-only testnet RPC** (`query_node_api`): allowlisted read-only endpoints
  against `KOVANICA_NODE_URL` (default `https://explorer.kovanica.online`);
  anything touching `mine`/`faucet`/`submit`/`operator` is rejected.
- **Persistent sessions** (`agent/checkpoint.py`): SQLite-backed LangGraph
  checkpointer (default `/data/agent.sqlite3` inside the container, on the
  `agent-data` volume) so conversation state survives restarts.
- **Human-gated apply → draft PR** (`agent/patchstore.py` + `agent/apply.py`):
  `git_diff_suggest` stages a proposal (path + explanation + unified diff) into
  the SQLite `patchstore`; on `/confirm` (dev role only), `apply.py` validates
  every path (rejects absolute, `..`, git metadata) and patch (`git apply
  --check`), applies them to a **throwaway git worktree** branched off
  `origin/main`, commits, pushes, and opens a **draft PR** via `gh`. It never
  mutates the main checkout. **Fail-closed**: unless `AGENT_GIT_APPLY_ENABLED=1`
  it only validates and reports (`dry_run`); `AGENT_GIT_DRY_RUN=1` forces a
  validate-only pass even when enabled. Env: `AGENT_GIT_REPO`,
  `AGENT_GIT_REMOTE` (default `origin`), `AGENT_GIT_BASE` (default `main`),
  `AGENT_GH_BIN` (default `gh`).

## Before this touches anything beyond your own machine
- [x] Public UI + nginx vhost for `kovi.kovanica.online` (loopback-only compose ports).
- [x] Index the repo once the stack is up: `deploy/vps-up.sh` does this on first run. Re-run `python -m indexer --repo /repos/kovanica-protocol` on merge.
- [x] Pre-vendor crate deps into the sandbox image at build time
      (`cargo fetch`) so `--offline` cargo calls actually succeed. Build via
      `docker compose --profile build-only build sandbox-image` (context is
      the repo root, not `sandbox/`, so the crate manifests resolve).
- [x] `sandbox-runner` API token (`SANDBOX_RUNNER_TOKEN`) — generated by `vps-up.sh`.
- [ ] Install gVisor (`runsc`) on the host and uncomment `runtime="runsc"`
      in `sandbox/runner/server.py` (the Docker-socket-owning sidecar is now
      the single place to set the sandbox runtime).
- [ ] Set real auth before arming `/confirm` for anyone but you: `AUTH_JWKS_URL` +
      `AUTH_ISSUER`/`AUTH_AUDIENCE`/`AUTH_DEV_ROLES` (Keycloak) or a strong
      `AUTH_DEV_TOKEN`. Without it everyone is `user` (safe by default).
- [ ] Arm the apply→PR path for a real repo: give the agent-api container a git
      identity + `gh` auth, set `AGENT_GIT_REPO` (or a read-only clone) and
      `AGENT_GIT_APPLY_ENABLED=1`. Until then `/confirm` returns a `dry_run`
      report only (safe by default).

## Layout
```
docker-compose.yml       full stack wiring (docker.sock owned by sandbox-runner only)
docker-compose.cpu.yml   VPS / no-GPU override (Ollama, loopback :13080)
deploy/                  nginx vhost + vps-up.sh
SYSTEM_PROMPT.md          agent's system prompt (vocab, citation rule, safety rules)
sandbox/
  Dockerfile              ephemeral cargo exec environment
  entrypoint.sh           whitelist enforcement inside the container
  runner/
    Dockerfile            sandbox-runner sidecar image (owns docker.sock)
    server.py             POST /run: whitelist + spawn sandbox container
    requirements.txt      docker SDK for the sidecar
agent/
  Dockerfile
  requirements.txt
  static/index.html       public Kovi chat UI
  main.py                 FastAPI: /, /chat, /confirm, /healthz
  auth.py                 JWT verification (JWKS or dev-token) → dev/user
  graph.py                LangGraph: router, tools, human gate
  rag.py                  Qdrant semantic search (search_codebase/explain_concept)
  indexer.py              Rust-aware chunking + indexing CLI
  embed.py                fastembed wrapper (bge-small-en-v1.5)
  checkpoint.py           SQLite persistent LangGraph checkpointer
  sandbox_client.py       run_cargo(command, args, repo_path) -> sidecar
```
