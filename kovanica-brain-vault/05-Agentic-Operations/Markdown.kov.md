# Markdown.kov — Vault Index

> Obsidian-compatible vault root note. Open `markdown-vault/` in Obsidian to browse.

**Created:** 2026-09-12  
**Purpose:** Kovanica agent brain — human-readable, git-trackable memory + knowledge

---

## Folder structure

```
markdown-vault/
├── README.md              # Vault conventions (Obsidian-compatible)
├── Markdown.kov.md        # This file — vault index + cross-reference map
├── Memory/                # Learned facts (YAML frontmatter + prose)
│   ├── .gitkeep
│   ├── current-branch-state.md          # Current branch + RFC-006 status
│   ├── rfc-006-tokenomics-numbers.md    # Canonical constants + code
│   └── kovanica-tool-surface.md             # Dev + user tool inventory
├── Chats/                 # Session transcripts + summaries
│   └── .gitkeep
├── Tasks/                 # Task lists per session/topic
│   └── .gitkeep
└── Notes/
    ├── .gitkeep
    ├── code-samples/
    │   ├── README.md                     # Key code samples indexed
    │   └── .gitkeep
    └── snapshots/
        ├── .gitkeep
        └── upgrade-progress-2026-09-12.md   # This session's snapshot
```

## How to use this vault

### For Kovanica (the agent)

1. **Learn something new** → write to `Memory/<slug>.md` with YAML frontmatter (`key`, `value`, `role`, `learned_at`, `source`).
2. **Session ends** → write transcript + summary to `Chats/<timestamp>-<session-id>.md`.
3. **Task changes** → update `Tasks/<topic or session>.md`.
4. **Important code/config/snapshot** → write to `Notes/code-samples/` or `Notes/snapshots/`.

### For Obsidian users

- Open the `markdown-vault/` folder as an Obsidian vault.
- Use `[[wikilink]]` syntax to cross-reference notes.
- Tags: `#rfcs`, `#tokenomics`, `#tooling`, `#session`, `#memory`, `#task`, `#code-sample`, `#snapshot`.
- YAML frontmatter is parsed as note metadata.

### For git

- All files are plain Markdown — diffable, reviewable, branchable.
- The vault is the durable layer; Qdrant + SQLite are runtime/semantic layers.

---

## Cross-reference map

| Topic | Skill file | Vault notes |
|-------|-----------|-------------|
| RFC-001 Multisig | `skills/rfc-001-multisig/SKILL.md` | `Notes/rfcs/rfc-001-multisig.md` |
| RFC-002 Multi-asset | `skills/rfc-002-multi-asset/SKILL.md` | `Notes/rfcs/rfc-002-multi-asset.md` |
| RFC-003 Stealth+script | `skills/rfc-003-stealth-script/SKILL.md` | `Notes/rfcs/rfc-003-stealth-script.md` |
| RFC-004 HTLC | `skills/rfc-004-htlc/SKILL.md` | `Notes/rfcs/rfc-004-htlc.md` |
| RFC-005 Vault | `skills/rfc-005-vault/SKILL.md` | `Notes/rfcs/rfc-005-vault.md` |
| RFC-006 Tokenomics | `skills/rfc-006-tokenomics/SKILL.md` | `Notes/rfcs/rfc-006-tokenomics.md` |
| Emission math | `skills/emission-math/SKILL.md` | `Notes/code-samples/emission-helper.rs` |
| API reference | `skills/api-reference/SKILL.md` | — |
| GHOSTDAG k=3 | `skills/ghostdag-notes/SKILL.md` | `Notes/rfcs/ghostdag-k3.md` |
| Operator matrix | `skills/operator-matrix/SKILL.md` | — |
| Node ops | `skills/node-ops/SKILL.md` | — |
| Project planning | `skills/project-planning/SKILL.md` | — |
| Rust client notes | `skills/rust-client-notes/SKILL.md` | `Notes/code-samples/ed25519-client.rs` |
| Mainnet checklist | `skills/mainnet-checklist/SKILL.md` | — |
| FAQ & pitfalls | `skills/faq-pitfalls/SKILL.md` | — |
| Cheat sheet | `skills/cheat-sheet/SKILL.md` | — |
| Scripts | `skills/scripts/SKILL.md` | — |
| Kovanica tool surface | — | `Memory/kovanica-tool-surface.md` |
| Current branch state | — | `Memory/current-branch-state.md` |
| Upgrade progress | — | `Notes/snapshots/upgrade-progress-2026-09-12.md` |

---

## Obisidian tips

- `[[Current Branch State]]` → links to `Memory/current-branch-state.md`
- `[[RFC-006 Tokenomics Numbers]]` → links to `Memory/rfc-006-tokenomics-numbers.md`
- `[[Kovanica Tool Surface]]` → links to `Memory/kovanica-tool-surface.md`
- `[[Upgrade Progress 2026-09-12]]` → links to `Notes/snapshots/upgrade-progress-2026-09-12.md`
- `#tokenomics` in any note → appears in tag pane

---

*Vault index — updated 2026-09-12. Add notes here as you create them.*
