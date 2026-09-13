# 02-State-UTXO — UTXO Ledger, State & Developer Skills

**Purpose**: UTXO ledger mechanics, state management, and developer reference skills.

## Contents

### Core Ledger Concepts

| File | Description |
|------|-------------|
| [skills-kovanica-blockchain-developer.md](skills-kovanica-blockchain-developer.md) | **Main developer skill** — protocol, GHOSTDAG, PHANTOM, tokenomics |
| [skills-api-reference.md](skills-api-reference.md) | API reference for tools and endpoints |
| [skills-cheat-sheet.md](skills-cheat-sheet.md) | Quick command reference |
| [skills-emission-math.md](skills-emission-math.md) | Emission curve, halving, subsidy calculations |
| [skills-ghostdag-notes.md](skills-ghostdag-notes.md) | GHOSTDAG algorithm notes |
| [skills-operator-matrix.md](skills-operator-matrix.md) | Operator command matrix |

### Developer Tools & Workflows

| File | Description |
|------|-------------|
| [skills-faq-pitfalls.md](skills-faq-pitfalls.md) | Common pitfalls and FAQ |
| [skills-scripts.md](skills-scripts.md) | Useful scripts and automation |
| [skills-rust-client-notes.md](skills-rust-client-notes.md) | Rust client patterns |
| [skills-project-planning.md](skills-project-planning.md) | Project planning templates |
| [skills-mainnet-checklist.md](skills-mainnet-checklist.md) | Mainnet deployment checklist |
| [skills-split-complete.md](skills-split-complete.md) | Skills split completion status |

### Reference Extracts

| File | Description |
|------|-------------|
| [MARKDOWN.god-extract.md](MARKDOWN.god-extract.md) | Comprehensive markdown extraction |
| [obsidian-vault-extract.md](obsidian-vault-extract.md) | Obsidian vault knowledge extract |
| [kovanica-tool-surface.md](kovanica-tool-surface.md) | Available tools and their usage |
| [current-branch-state.md](current-branch-state.md) | Current development branch state |

### Implementation Skills (from /root/rust/skills/)

| File | Description |
|------|-------------|
| [skills/rust-utxo-ledger/SKILL.md](skills/rust-utxo-ledger/SKILL.md) | **UTXO ledger implementation** — UTXO model, tx validation, double-spend prevention, UTXO set management, block application |

## Key Concepts

- **UTXO Model**: Ed25519 spend authorization, per-block state
- **Address Versions**: P2PK (0x00), P2SH (0x01), Script v2 (0x02), Stealth (0x03), HTLC (0x04), Vault (0x05)
- **Checkpoint Versions**: v3 (stake), v4 (assets), v5 (stealth/script), v6 (vault/CSV)
- **Activation Gating**: Blue-score gated consensus upgrades
- **Finality**: Depth-based pruning, implicit re-orgs

## Crate Reference

- `crates/kovanica-state` — UTXO ledger, transactions, validation, snapshots
- `crates/kovanica-node` — Node RPC, mempool, block production