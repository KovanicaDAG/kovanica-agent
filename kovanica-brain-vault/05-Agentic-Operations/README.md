# 05-Agentic-Operations — Agent Workflows, Skills & Operations

**Purpose**: Agentic workflows, skills system, and operational procedures for AI agents.

## Contents

| File | Description |
|------|-------------|
| [Markdown.kov.md](Markdown.kov.md) | Kovanica markdown format specification |
| [README.md](README.md) | Agent workspace overview |

## Agent Skills System

### Skill Structure
```
skills/
├── skill-name/
│   ├── SKILL.md          # Skill manifest (auto-activating)
│   ├── references/       # Reference documents
│   └── scripts/          # Helper scripts
```

### Core Skills (Bundled)
- **kovanica-blockchain-developer** — Protocol expertise, GHOSTDAG, tokenomics
- **rust-developer** — Rust best practices, async, cargo workflows
- **code-reviewer** — Security, performance, maintainability review

### Skill Activation
- **Auto-activating**: Based on conversation context (keywords, file patterns)
- **Manual**: `/skills enable <name>` / `/skills disable <name>`
- **Namespaced**: `skill_view("namespace:skill-name")`

## Agent Workflows

### Coding Loop
1. **Search** → `search_codebase` / `search_kovanica_docs`
2. **Read** → `read_file` with citations
3. **Propose** → `git_diff_suggest` (dev role)
4. **Verify** → `run_cargo_command` (check/test/clippy/build)
5. **Confirm** → `/confirm` with dev token → applies to throwaway worktree

### Session Management
- **Persistent**: SQLite checkpoints (`/data/agent.sqlite3`)
- **Transcripts**: JSONL format, portable across restarts
- **Fork/Resume**: `--resume`, `--continue`, `--fork` CLI flags

### Memory Providers
- **Local**: JSONL storage (default)
- **SQLite**: Structured queries
- **Vector**: Chroma/Pinecone (semantic search)
- **ByteRover**: Hierarchical knowledge tree
- **Supermemory**: Semantic graph API

## Agent Tools

| Tool | Role | Purpose |
|------|------|---------|
| `search_codebase` | user/dev | Semantic + keyword code search |
| `search_kovanica_docs` | user/dev | Skill docs search |
| `explain_concept` | user/dev | Protocol term explanations |
| `read_file` | user/dev | Read repo files |
| `query_node_api` | user/dev | Read-only node RPC |
| `git_diff_suggest` | dev | Propose patches |
| `run_cargo_command` | dev | Cargo check/test/clippy/build |
| `run_kovanica_cli` | dev | CLI wallet commands |

## Configuration

- **System Prompt**: `SYSTEM_PROMPT.md` (vocab, citation rules, safety)
- **Auth**: JWT (JWKS) or dev shared-secret (`AUTH_DEV_TOKEN`)
- **Roles**: `user` (read-only) vs `dev` (full tools)
- **Sandbox**: Network-disabled, 2GB/2CPU, user=sandbox

### Implementation Skills (from /root/rust/skills/)

| File | Description |
|------|-------------|
| [skills/rust-async/SKILL.md](skills/rust-async/SKILL.md) | **Async Rust** — tokio, async-std, futures, async traits, spawn |
| [skills/rust-error-handling/SKILL.md](skills/rust-error-handling/SKILL.md) | **Error handling** — thiserror, anyhow, eyre, snafu, miette, error chain |
| [skills/rust-logging-tracing/SKILL.md](skills/rust-logging-tracing/SKILL.md) | **Logging & tracing** — tracing, tracing-subscriber, log, env_logger, spans |
| [skills/rust-serialization/SKILL.md](skills/rust-serialization/SKILL.md) | **Serialization** — serde, serde_json, bincode, postcard, rkyv, prost |
| [skills/rust-testing/SKILL.md](skills/rust-testing/SKILL.md) | **Testing** — unit/integration tests, proptest, cargo-fuzz, mockall |
| [skills/rust-performance/SKILL.md](skills/rust-performance/SKILL.md) | **Performance** — perf, flamegraph, criterion, allocator tuning, SIMD |
| [skills/rust-crypto/SKILL.md](skills/rust-crypto/SKILL.md) | **Rust crypto** — ring, ed25519-dalek, blake3, sha2, aes-gcm, rand, hkdf |

## Crate Reference

- `agent/` — FastAPI `/chat`, `/confirm`, `/healthz`
- `agent/graph.py` — LangGraph router, tools, human gate
- `agent/rag.py` — Qdrant semantic search
- `agent/checkpoint.py` — SQLite LangGraph checkpointer