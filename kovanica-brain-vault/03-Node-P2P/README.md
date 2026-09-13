# 03-Node-P2P — Node Operations, P2P Mesh & Networking

**Purpose**: Runnable node, P2P gossip, networking, and operational runbooks.

## Contents

| File | Description |
|------|-------------|
| [OPERATIONS.md](OPERATIONS.md) | **Seed ops runbook** — backup/restore, restart drill, post-deploy checks |
| [README.md](README.md) | Protocol README (from kovanica-protocol) |
| [skills-node-ops.md](skills-node-ops.md) | Node operations skill summary |
| [upgrade-progress-2026-09-12.md](upgrade-progress-2026-09-12.md) | Upgrade progress snapshot |
| [obsidian-vault-extraction-2026-09-12.md](obsidian-vault-extraction-2026-09-12.md) | Vault extraction notes |

## Key Components

### Node Binary (`crates/kovanica-node`)
- **RPC**: Line-based text protocol (`execute_line`)
- **Mempool**: Deterministic ordering, orphan pool, fee eviction
- **Block Production**: `produce` command, multi-input transfers
- **Explorer**: Self-hosted JSON API + WebSocket UI (`/ws`)

### P2P Mesh (`p2p.rs`, `net.rs`, `relay.rs`)
- **Discovery**: Hello advertisements, DNS seeds, Kademlia DHT
- **Gossip**: Delayed relay loop, block+tx flood
- **Sync**: Framed bidirectional TCP (`pull_blocks_timeout`/`serve_exchange`)
- **Hardening**: Rate limiting, duplicate suppression, peer scoring/banning

### Networking
- **Dual-stack**: IPv4 + IPv6 listeners (`0.0.0.0:P` + `[::]:P`)
- **WebSocket**: Explorer `/ws` endpoint, live block/tx updates
- **CORS Proxy**: Explorer proxy for web UI

## Operational Endpoints

| Endpoint | Purpose |
|----------|---------|
| `seed.kovanica.online:9000` | Bootstrap peer |
| `explorer.kovanica.online` | Explorer & API |
| `https://kovanica.kovanica.online` | Kovanica UI |

### Implementation Skills (from /root/rust/skills/)

| File | Description |
|------|-------------|
| [skills/rust-p2p-networking/SKILL.md](skills/rust-p2p-networking/SKILL.md) | **P2P networking** — libp2p, Kademlia DHT, gossipsub, peer discovery, NAT traversal |
| [skills/rust-mempool/SKILL.md](skills/rust-mempool/SKILL.md) | **Mempool implementation** — tx validation, fee ordering, replacement, eviction, propagation |
| [skills/rust-block-propagation/SKILL.md](skills/rust-block-propagation/SKILL.md) | **Block propagation** — header-first, compact blocks, tx requests, flood control, orphan handling |

## Crate Reference

- `crates/kovanica-node` — Node, mempool, P2P, RPC, explorer
- `crates/kovanica-dag` — Consensus (used by node)
- `crates/kovanica-state` — Ledger (used by node)