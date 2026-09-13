---
source: skills/kovanica-blockchain-developer/SKILL.md
name: kovanica-blockchain-developer
synced_at: 2026-09-12T08:33:08.793562+00:00
synced_from: skills
tags: [skill, kovanica]
---
# kovanica-blockchain-developer — synced from skills/kovanica-blockchain-developer/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.793562+00:00

# Kovanica Blockchain Developer — Skill Entry Point

```yaml
name: kovanica-blockchain-developer
description: >
  Kovanica Protocol (KovanicaDAG) engineering agent — Rust-based GHOSTDAG BlockDAG
  with UTXO ledger and Ed25519 signatures. Native token KVNC (8 decimals).
  Current public network: testnet kovanica-testnet.
```

## Overview

Specialize in the Kovanica Protocol (KovanicaDAG) — a Rust-based GHOSTDAG BlockDAG with UTXO ledger and Ed25519 signatures. Native token **KVNC** (8 decimals). Current public network is testnet `kovanica-testnet`.

**Shipped RFCs / KVP standards** (see `rfcs-index/SKILL.md`):
- RFC-001 / KVP-101 — Multisig (M-of-N P2SH)
- RFC-002 / KVP-102 — Native multi-asset tokens
- RFC-003 / KVP-103 — Stealth + script v2
- RFC-004 / KVP-104 — HTLC atomic swaps
- RFC-005 / KVP-105 — Time-lock vault + CSV
- RFC-006 — Tokenomics (steps 1–4 landed; activation pending)

## Core Architecture

- Consensus — GHOSTDAG with parameter `k=3`
- Ledger — UTXO model
- Signatures — Ed25519 (64-byte sigs → 128 hex)
- Native token — KVNC (1 KVNC = 100_000_000 atoms)
- P2P — plaintext TCP only on port 9000 (no libp2p)
- Bootstrap seed — `seed.kovanica.online:9000` (DNS-only / grey-cloud)
- Explorer / API — https://explorer.kovanica.online
- Wallet — https://wallet.kovanica.online (node never sees seeds)

Key crates (monorepo layout):
- `kovanica-dag` — DAG + GHOSTDAG consensus
- `kovanica-state` — UTXO ledger
- `kovanica-node` — node binary
- `kovanica-cli` — CLI wallet

## Official Resources

- Site — https://kovanica.online
- Explorer — https://explorer.kovanica.online
- Wallet — https://wallet.kovanica.online
- Node (binary dist) — https://github.com/KovanicaDAG/kovanica-node
- Protocol monorepo (preferred for dev) — https://github.com/KovanicaDAG/kovanica-protocol
- One-click install — `curl -sSfL https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.sh | bash`

## Tokenomics (RFC-006) — Canonical

**Load full details from `rfc-006-tokenomics/SKILL.md`.**

Key numbers:

| Item                    | Value                                      |
|-------------------------|--------------------------------------------|
| Max supply              | 90.2M KVNC (`90_200_000_000_000_000` atoms)|
| Curve emission          | 80M KVNC (smooth geometric decay)          |
| Founder premine         | 0.2M KVNC                                  |
| Treasury (vested)       | 10M KVNC (10 × 1M RFC-005 vaults)          |
| Genesis subsidy s₀      | 10 KVNC / block                            |
| Era length              | 2_000_000 blocks                           |
| Decay α                 | 3/4 per era                                |
| Coinbase maturity       | 100 blocks                                 |
| Fee split               | 75% burned / 25% to producer               |
| Fee floor               | `max(1, subsidy / 500_000)` atoms per byte |

Implementation status (per RFC):
- Steps 1–4 (emission curve, MAX_SUPPLY, maturity, fee burn) landed & green (785 tests).
- Steps 5–6 (treasury genesis + mainnet profile) and Step 7 (supply accounting) still pending.
- Activation is a consensus fork; testnet will reset.

Always prefer the RFC-006 numbers over any older live `/api/head` values once the branch is merged and activated.

## Live Parameters (pre-RFC-006 testnet)

Call `GET /api/head` before hard-coding values on the *current* public testnet. Example shape (will change after reset):

```json
{
  "network": "kovanica-testnet",
  "genesis": "3beecbebb6103ee24d1617fd87e920c949d613febbbcf6ca1453f3a4bf74056e",
  "tip": "<current>",
  "blocks": <height>,
  "min_fee": 40000,
  "atom": 100000000
}
```

## Progressive Disclosure — Detailed References

Load these on demand:

**RFC / KVP standards**
- `rfcs-index/SKILL.md` — status table for RFC-001…006 / KVP-101…105
- `rfc-001-multisig/SKILL.md` — KVP-101 M-of-N P2SH
- `rfc-002-multi-asset/SKILL.md` — KVP-102 native multi-asset tokens
- `rfc-003-stealth-script/SKILL.md` — KVP-103 stealth + script v2
- `rfc-004-htlc/SKILL.md` — KVP-104 HTLC atomic swaps
- `rfc-005-vault/SKILL.md` — KVP-105 time-lock vault + CSV (treasury & escrow)
- `rfc-006-tokenomics/SKILL.md` — full RFC-006 (emission, cap, maturity, fees, treasury)
- `rfc-006-activation/SKILL.md` — migration playbook, testnet-reset impact

**Core protocol & ops**
- `emission-math/SKILL.md` — subsidy_at, fee floor, maturity helpers + constants
- `api-reference/SKILL.md` — endpoint table, pre/post-RFC-006 /api/head shapes, new ledger errors
- `ghostdag-notes/SKILL.md` — k=3 implications, blue work, parallel minting vs hard cap
- `operator-matrix/SKILL.md` — safe flag sets for home / explorer / seed / miner roles
- `node-ops/SKILL.md` — env vars, seed vs clone, build & verification
- `project-planning/SKILL.md` — layered decomposition, phase sequencing, risk register
- `rust-client-notes/SKILL.md` — Ed25519 signing, client skeleton, post-RFC-006 checklist

**Ops, planning & quick ref**
- `mainnet-checklist/SKILL.md` — go/no-go checklist before mainnet
- `faq-pitfalls/SKILL.md` — common mistakes and answers
- `cheat-sheet/SKILL.md` — one-page constants, commands, URLs

**Scripts**
- `scripts/SKILL.md` — check-head.sh, emission.rs

## Quick Node Start (participant)

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

Critical:
- Use DNS-only seed name (or origin IP). Never point peers at the Cloudflare orange-cloud explorer hostname for TCP 9000.
- Preserve `KOVANICA_DATA` after first genesis write.
- After sync, local `/api/head` must match public genesis (and tip).

## Transaction Flow (wallet-style)

1. `POST /api/prepare` → receive sighash + fee + change
2. Sign sighash offline with Ed25519 → 64-byte sig (128 hex)
3. `POST /api/submit` with the signed transaction

Node never receives seed or private key. After RFC-006 activation the fee floor and burn rules apply; immature coinbases are automatically skipped by the transaction builder.

## Multisig

RFC-001 style M-of-N P2SH:
- Create spend proposals
- Collect partial signatures
- Combine and broadcast

Prefer official wallet / CLI for production flows until custom tooling is fully validated.

## Development Workflow

1. Prefer monorepo (`kovanica-protocol`) for any change to dag / state / node / cli.
2. Work on RFC-006 lives on branch `tokenomics/rfc-006-emission-curve`.
3. Always verify live parameters via `/api/head` and `/api/bootstrap` on the active network.
4. Keep all private key material strictly client-side.
5. Target the documented HTTP API + Ed25519 sighash for any new client library.
6. When planning features, force the three-layer split (consensus-safe / ledger-safe / client-only) and surface the risk register early.
7. Treat MAX_SUPPLY, maturity, and fee-burn as hard consensus rules once activated.

## Project Planning Stance

Act as project-plan mastermind:
- Sequence around testnet stability → RFC-006 activation (with reset) → API stability → wallet/UX → advanced features → mainnet readiness.
- Produce concrete milestone tables with exit criteria.
- Call out P2P, fee, GHOSTDAG-k, supply-cap, maturity, and seed-handling risks explicitly.
- Prefer actionable checklists over vague recommendations.

## Safety Rules

- Never recommend `KOVANICA_ALLOW_RESET=1` or open faucet on public-facing nodes without explicit isolation.
- Default participant config keeps `MINE=0` and `FAUCET=0`.
- Document every environment variable in any run script or README you generate.
- Keep private keys and seeds out of node processes, logs, and API payloads.
- After RFC-006 activation, enforce the 90.2M hard cap and 100-block coinbase maturity in all tooling.

When the user asks for code, configs, or plans, produce 

... (truncated, see /root/kovanica-agent/skills/kovanica-blockchain-developer/SKILL.md for full content)