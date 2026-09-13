---
source: skills/node-ops/SKILL.md
name: node-ops
synced_at: 2026-09-12T08:33:08.794198+00:00
synced_from: skills
tags: [skill, kovanica]
---
# node-ops — synced from skills/node-ops/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.794198+00:00

# Kovanica Node Operations

## Environment Variables

| Variable | Typical value | Purpose |
|----------|---------------|---------|
| `KOVANICA_POW` | `1` | Enable PoW |
| `KOVANICA_MINE` | `0` | Disable automatic empty-block mining |
| `KOVANICA_MINE_SECS` | `120` | Minimum seconds between mined blocks when mining is on |
| `KOVANICA_FAUCET` | `0` | Disable open faucet |
| `KOVANICA_ALLOW_RESET` | `0` | Disable dangerous reset |
| `KOVANICA_OPERATOR` | `0` | Disable operator-only controls |
| `KOVANICA_LISTEN` | `0.0.0.0:9000` | P2P TCP listen address |
| `KOVANICA_PEERS` | `seed.kovanica.online:9000` | Comma-separated bootstrap peers |
| `KOVANICA_DATA` | `$PWD/data` | Persistent data directory (genesis + chain) |

## Recommended Public Participant Config

```sh
export KOVANICA_POW=1
export KOVANICA_MINE=0
export KOVANICA_MINE_SECS=120
export KOVANICA_FAUCET=0
export KOVANICA_ALLOW_RESET=0
export KOVANICA_OPERATOR=0
export KOVANICA_LISTEN=0.0.0.0:9000
export KOVANICA_PEERS=seed.kovanica.online:9000
export KOVANICA_DATA="$PWD/data"

./target/release/kovanica-node explorer 127.0.0.1:8080
```

## Seed Node Notes

- Seed should set `KOVANICA_PEERS=off` (or empty) so it does not dial itself.
- Clones must dial a **DNS-only** (grey-cloud) hostname or the origin IP.
- Do **not** point peers at `explorer.kovanica.online:9000` — Cloudflare does not proxy port 9000.

## Build

```sh
# Preferred for development
git clone https://github.com/KovanicaDAG/kovanica-protocol.git
cd kovanica-protocol
cargo build --release -p kovanica-node

# Binary distribution mirror
git clone https://github.com/KovanicaDAG/kovanica-node.git
```

One-click install (no git required):

```sh
curl -sSfL https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.ps1 | iex
```

## Verification After Sync

```sh
curl -s http://127.0.0.1:8080/api/head
curl -s https://explorer.kovanica.online/api/head
```

Genesis and (after full catch-up) tip should match.

## Data Directory

First start writes the genesis block into `KOVANICA_DATA`.  
Treat this directory as permanent state — do not delete it if you want to keep the local chain view.
