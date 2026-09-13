# Kovanica Brain Vault

**The canonical knowledge base for the Kovanica protocol and agent.**

> **Structure**: Organized by protocol layer (00-05) following the kovanica-protocol crate architecture.

---

## Vault Structure

```
kovanica-brain-vault/
├── .agent/                    # Agent directives & invariants
├── 00-Meta/                   # Project overview, governance, environment
├── 01-Consensus-DAG/          # GHOSTDAG consensus, RFCs, tokenomics
├── 02-State-UTXO/             # UTXO ledger, state, developer skills
├── 03-Node-P2P/               # Node ops, P2P mesh, networking
├── 04-Clients-LightNodes/     # Light clients, FFI, mobile
└── 05-Agentic-Operations/     # Agent workflows, skills, operations
```

---

## Quick Navigation

| Layer | Directory | Key Files |
|-------|-----------|-----------|
| **Meta** | [00-Meta/](00-Meta/) | [AGENTS.md](00-Meta/AGENTS.md), [KOVANICA.md](00-Meta/KOVANICA.md), [ENVIRONMENT.md](00-Meta/ENVIRONMENT.md) |
| **Consensus** | [01-Consensus-DAG/](01-Consensus-DAG/) | [RFC-001..005](01-Consensus-DAG/), [TOKENOMICS.md](01-Consensus-DAG/TOKENOMICS.md) |
| **State** | [02-State-UTXO/](02-State-UTXO/) | [skills-kovanica-blockchain-developer.md](02-State-UTXO/skills-kovanica-blockchain-developer.md), [skills-api-reference.md](02-State-UTXO/skills-api-reference.md) |
| **Node/P2P** | [03-Node-P2P/](03-Node-P2P/) | [OPERATIONS.md](03-Node-P2P/OPERATIONS.md), [skills-node-ops.md](03-Node-P2P/skills-node-ops.md) |
| **Clients** | [04-Clients-LightNodes/](04-Clients-LightNodes/) | [skills-rust-client-notes.md](04-Clients-LightNodes/skills-rust-client-notes.md) |
| **Agentic** | [05-Agentic-Operations/](05-Agentic-Operations/) | [Markdown.kov.md](05-Agentic-Operations/Markdown.kov.md) |

---

## Protocol Overview

**Kovanica** is a **DAG-based distributed ledger** (BlockDAG) using **GHOSTDAG** consensus (Kaspa protocol).

### Core Crates

| Crate | Purpose |
|-------|---------|
| `kovanica-dag` | DAG + GHOSTDAG consensus core |
| `kovanica-state` | UTXO ledger in GHOSTDAG order |
| `kovanica-node` | Runnable node, RPC, P2P, mempool |
| `kovanica-ffi` | UniFFI bindings for light nodes |
| `kovanica-cli` | CLI wallet |

### Consensus Upgrades (RFCs)

| RFC | Feature | Address Version | Activation |
|-----|---------|-----------------|------------|
| 001 | Multisig (M-of-N, P2SH) | 0x01 | Blue score |
| 002 | Native Tokens (multi-asset) | — | Blue score |
| 003 | Stealth + Script v2 | 0x02, 0x03 | Blue score |
| 004 | HTLC + Atomic Swaps | 0x04 | Blue score |
| 005 | Vault + CSV | 0x05 | Blue score |

### Network Endpoints

| Service | URL |
|---------|-----|
| P2P Bootstrap | `seed.kovanica.online:9000` |
| Explorer & API | `https://explorer.kovanica.online` |
| Kovanica UI | `https://kovanica.kovanica.online` |
| Agent API (local) | `http://localhost:13080` |

---

## For AI Agents

### Start Here
1. **Read [AGENTS.md](00-Meta/AGENTS.md)** — Conventions, layout, roadmap
2. **Read [SYSTEM_RULES.md](.agent/SYSTEM_RULES.md)** — Technical invariants
3. **Review [KOVANICA.md](00-Meta/KOVANICA.md)** — Tool surface, safety, conventions

### Coding Workflow
```
search_codebase → read_file → git_diff_suggest → run_cargo_command → /confirm
```

### Key Skills
- `kovanica-blockchain-developer` — Protocol expertise
- `rust-developer` — Rust patterns
- `code-reviewer` — Security/performance review

### Memory Providers
- Local (JSONL) — Default
- SQLite — Structured
- Vector — Semantic search
- ByteRover — Hierarchical knowledge
- Supermemory — Semantic graph

---

## For Developers

### Build & Test
```bash
cargo build              # Build all
cargo test               # Unit + integration + doctests
cargo clippy --all-targets  # Lint
cargo fmt --check        # Format check
```

### Run Node
```bash
cargo run -p kovanica-node -- demo   # Scripted scenario
cargo run -p kovanica-node           # REPL (try `help`)
```

### Light Node (Mobile)
```bash
# Android
./crates/kovanica-ffi/build-android.sh

# iOS/macOS
./crates/kovanica-ffi/build-apple.sh
```

---

## For Operators

### Seed Operations
- **Runbook**: [OPERATIONS.md](03-Node-P2P/OPERATIONS.md)
- **Backup**: `data/` directory (DAG + ledger snapshots)
- **Restart**: pm2 restart + post-deploy checks

### Monitoring
- **Metrics**: Prometheus (`/metrics` on node)
- **Explorer**: `explorer.kovanica.online`
- **Logs**: pm2 logs / docker compose logs

---

## Maintenance

### Updating the Vault
1. Source of truth: `kovanica-protocol/` repository
2. RFCs: `kovanica-protocol/docs/RFC-*.md`
3. AGENTS.md: `kovanica-protocol/AGENTS.md`
4. Sync periodically with `rsync` or manual copy

### Cleanup Rules
- Keep only `.md` files in vault directories
- Archive old snapshots to `archive/`
- Remove duplicate/outdated skill files
- Maintain README.md index in each directory

---

## Version
- **Vault version**: 1.0
- **Protocol**: kovanica-protocol (BlockDAG + GHOSTDAG)
- **Last sync**: 2026-09-13
- **Source commit**: kovanica-protocol HEAD