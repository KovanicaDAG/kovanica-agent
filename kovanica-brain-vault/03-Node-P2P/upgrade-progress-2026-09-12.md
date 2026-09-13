# Snapshot — Kovanica Agent Upgrade Progress

> Point-in-time snapshot of Kovanica agent upgrade state.
> Updated: 2026-09-12

---

## What was done in this session

### 1. Skill pack split (monolithic → per-skill)

The monolithic `SKILL.md` (1374 lines, 56KB) was split into 19 per-skill files under `skills/<skill-name>/SKILL.md`:

| # | Skill folder | Lines | Content |
|---|-------------|-------|---------|
| 1 | `kovanica-blockchain-developer/` | 214 | Entry point + overview + quick reference |
| 2 | `rfcs-index/` | 47 | RFC/KVP status table + quick guidance |
| 3 | `rfc-001-multisig/` | 36 | KVP-101 M-of-N P2SH |
| 4 | `rfc-002-multi-asset/` | 40 | KVP-102 native multi-asset tokens |
| 5 | `rfc-003-stealth-script/` | 37 | KVP-103 stealth + script v2 |
| 6 | `rfc-004-htlc/` | 30 | KVP-104 HTLC atomic swaps |
| 7 | `rfc-005-vault/` | 60 | KVP-105 time-lock vault + CSV, treasury vesting |
| 8 | `rfc-006-tokenomics/` | 157 | Full RFC-006 spec (emission, cap, maturity, fees, treasury) |
| 9 | `rfc-006-activation/` | 117 | Activation playbook, testnet reset, client checklist |
| 10 | `emission-math/` | 80 | subsidy_at, fee_floor, maturity helpers + constants |
| 11 | `api-reference/` | 107 | Endpoint table, pre/post-RFC-006 shapes, error conditions |
| 12 | `ghostdag-notes/` | 40 | k=3 implications, blue work, parallel minting vs hard cap |
| 13 | `operator-matrix/` | 37 | Safe flag sets for home/explorer/seed/miner roles |
| 14 | `node-ops/` | 55 | Env vars, seed vs clone, build & verification |
| 15 | `project-planning/` | 85 | Layered decomposition, phase sequencing, risk register |
| 16 | `rust-client-notes/` | 70 | Ed25519 signing, client skeleton, post-RFC-006 checklist |
| 17 | `mainnet-checklist/` | 45 | Go/no-go checklist before mainnet |
| 18 | `faq-pitfalls/` | 50 | Common mistakes and answers |
| 19 | `cheat-sheet/` | 42 | One-page constants, commands, URLs |
| 20 | `scripts/` | 65 | check-head.sh, emission.rs |

**Original `SKILL.md` kept in place** but now points to per-skill files for progressive disclosure.

### 2. Vault structure created (`markdown-vault/`)

```
markdown-vault/
├── README.md              # Vault conventions (Obsidian-compatible)
├── Markdown.kov.md        # Vault index + cross-reference map
├── Memory/
│   ├── .gitkeep
│   ├── current-branch-state.md          # Current branch + RFC-006 status
│   ├── rfc-006-tokenomics-numbers.md    # Canonical constants + code
│   └── kovanica-tool-surface.md             # Dev + user tool inventory
├── Chats/
│   └── .gitkeep
├── Tasks/
│   └── .gitkeep
└── Notes/
    ├── .gitkeep
    └── code-samples/
        └── README.md                     # Key code samples indexed
        └── .gitkeep
```

### 3. Vault memory notes written

| Note | Purpose |
|------|---------|
| `Memory/current-branch-state.md` | Current branch, RFC-006 status, key numbers, cross-refs |
| `Memory/rfc-006-tokenomics-numbers.md` | Canonical constants with Rust code snippets |
| `Memory/kovanica-tool-surface.md` | Full dev + user tool inventory with safety notes |

### 4. Cross-link map

`Markdown.kov.md` contains a full cross-reference table mapping each skill file to its expected vault note location. The map is the "source of truth" for where knowledge lives.

---

## What's pending

- `Chats/` notes — session transcripts (written at session end by `_write_session_to_vault`)
- `Tasks/` notes — task lists (written by task management tools)
- `Notes/rfcs/*.md` — detailed RFC notes mirroring skill content
- `Notes/snapshots/` — future point-in-time state captures
- Real integration test: running `kovanica repl` end-to-end with vault writes

---

## How to continue

1. Add more vault memory notes as new facts are learned: write `Memory/<slug>.md` with YAML frontmatter.
2. Add code samples to `Notes/code-samples/` when implementing new features.
3. Take snapshots in `Notes/snapshots/` before major changes.
4. Use `[[wikilink]]` syntax in Obsidian to cross-reference notes.
5. Tag notes with `#rfcs`, `#tokenomics`, `#tooling`, `#code-sample`, `#snapshot`.
