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

## How to use Kovi to actually code

Kovi is a coding assistant that **reads your repo first** and **proposes patches
second**. The loop is: ask → Kovi searches the codebase → Kovi answers with file
citations → (optionally) Kovi proposes a `git_diff_suggest` patch → you
review → `/confirm` applies it to a throwaway worktree (and, when armed, opens a
draft PR). You never give Kovi a shell, and Kovi never pushes to your main branch
directly.

### One-time setup: the dev token

`/confirm` (and therefore patch approval) requires the `dev` role. Copy
`.env.example` → `.env` and generate a shared-secret bearer token:

```bash
cp .env.example .env
openssl rand -hex 24   # paste the result into AUTH_DEV_TOKEN= in .env
```

`docker compose` reads `.env` automatically. A request that carries
`Authorization: Bearer <that token>` maps to `dev`; everything else maps to
`user`. Without a real token set, everyone is `user` (read-only tools) — safe by
default.

### The actual coding loop

**Chat with Kovi** via `POST /chat`. Carry a stable `session_id` so the
conversation persists across restarts (SQLite checkpoint, `agent-data` volume).
Example with `curl`:

```bash
# user role (no token): read-only tools — code search, skill-docs search, node API
curl -s -X POST http://localhost:13080/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"sess-1","message":"how is GHOSTDAG selection implemented"}'

# dev role (your AUTH_DEV_TOKEN): full tool set — also git_diff_suggest, run_cargo
TOKEN="d1acc8370cd74fc94b2c2464cd004409d76f4a9ebd7fc719"
curl -s -X POST http://localhost:13080/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id":"sess-1","message":"..." }'
```

**What Kovi does with your message:**

1. It runs `search_codebase` over the indexed repo (Qdrant `kovanica_codebase`)
   and, when relevant, `search_kovanica_docs` over the skill's RFCs/tokenomics/
   GHOSTDAG notes. This is the RAG step — Kovi reads before it answers.
2. It builds a system prompt from `SYSTEM_PROMPT.md` plus the retrieved context,
   then calls the LLM.
3. It returns prose with **file-path citations** from the retrieved context. It
   does not invent paths. If you ask about something not in the index, it says so
   rather than hallucinating a crate.

**Prompts that work** (grounded, repo-shaped, concrete):

- "How is `selected_parent` / blue-work computed in `kovanica-dag`?"
- "Find the fee-floor logic and show me the current value for height N."
- "Where are Ed25519 signatures constructed and submitted in the client path?"
- "This function in `kovanica-state` looks O(n^2) — suggest a fix and cite the file."
- "Add a `--verbose` flag to this CLI subcommand and show me the diff."
- "Explain RFC-006 emission curve and the MAX_SUPPLY hard cap."

**Prompts that don't work well:** vague ones ("make the code better"), requests
that depend on files not yet indexed, and anything that requires Kovi to read your
local files outside the repo mount.

### Proposing and applying patches (dev role)

When you ask Kovi to change code, it can call `git_diff_suggest` (dev role only).
That tool:

- reads the relevant files from the read-only repo mount,
- produces a unified diff + short explanation + the file path,
- stores the proposal in the SQLite `patchstore` under your `session_id`.

You then call `POST /confirm` with your dev token and the proposal:

```bash
curl -s -X POST http://localhost:13080/confirm \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"session_id":"sess-1","approve":true}'
```

What `/confirm` actually does (fail-closed by default):

- **Validates** every proposed path (rejects absolute paths, `..`, and git metadata
  paths) and every patch (`git apply --check`).
- **Applies** the validated patches to a **throwaway git worktree** branched off
  `origin/main` — it never mutates the main checkout.
- **Optionally** commits, pushes, and opens a **draft PR** via `gh` — but only when
  `AGENT_GIT_APPLY_ENABLED=1` is set and the container has a git identity + `gh`
  auth. Until then `/confirm` returns a `dry_run` report only. `AGENT_GIT_DRY_RUN=1`
  forces validate-only even when enabled.

You review the applied patches in the throwaway worktree (or the draft PR) before
merging. Kovi does not merge anything.

### Letting Kovi verify with the sandbox

Kovi's `run_cargo_command` tool runs `cargo check|test|clippy|build` inside an
ephemeral, network-disabled sandbox container. Use it to answer "does this
compile?" and "are the tests green?" without giving Kovi a shell. Only those four
commands are whitelisted, both client-side (`sandbox_client.py`) and server-side
(`sandbox/runner/server.py`), so a compromised agent-api can never drive arbitrary
containers.

### Iterate

If a patch is off, tell Kovi what to change in the same session and re-prompt.
The retrieved context and checkpoint carry over, so Kovi can refine the proposal in
place. If it keeps going in the wrong direction, reject at `/confirm` and start a
fresh `session_id`.

### What Kovi cannot do (boundaries)

- No arbitrary shell. Only the four whitelisted `cargo` commands, inside a
  network-disabled sandbox.
- No pushing to your main branch. Only throwaway worktrees + (optionally) draft
  PRs from `/confirm`, and only when you arm `AGENT_GIT_APPLY_ENABLED=1`.
- No reading your local files outside the repo mount. It only sees what the index
  + the read-only repo bind give it.
- No tool-call JSON in the chat reply. The HTTP interface is prose/JSON, not a
  tool-execution surface — tool calls happen server-side inside the graph.

### Roles at a glance

| Role | How you get it | Tools available |
|------|----------------|-----------------|
| `user` | no token, or wrong token | `search_codebase`, `search_kovanica_docs`, `query_node_api` (read-only) |
| `dev` | `Authorization: Bearer <AUTH_DEV_TOKEN>` | everything above + `git_diff_suggest`, `run_cargo_command`, `read_file` |

The live `/healthz` tells you the stack is up:
`curl -s http://localhost:13080/healthz` → `{"status":"ok","name":"kovi"}`.

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
  `sandbox_client.run_cargo(command, args, repo_path)` (`agent/sandbox_client.py`).
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
- [x] gVisor (`runsc`) installed on the host and `runtime="runsc"` uncommented
      in `sandbox/runner/server.py` (the Docker-socket-owning sidecar is now
      the single place to set the sandbox runtime).
- [x] Real auth before arming `/confirm` for anyone but you: `AUTH_JWKS_URL` +
      `AUTH_ISSUER`/`AUTH_AUDIENCE`/`AUTH_DEV_ROLES` (Keycloak) or a strong
      `AUTH_DEV_TOKEN`. Without it everyone is `user` (safe by default).
- [x] Arm the apply→PR path for a real repo: give the agent-api container a git
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
