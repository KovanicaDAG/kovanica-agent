---
key: skills-split-complete
value: "Monolithic SKILL.md (1374 lines, 56KB) split into 20 per-skill files under skills/<skill-name>/SKILL.md on 2026-09-12. Entry point: skills/kovanica-blockchain-developer/SKILL.md. Vault: markdown-vault/ (Obsidian-compatible). See skills/README.md for index."
role: dev
learned_at: 2026-09-12T00:00:00+00:00
source: SKILL.md + skills/README.md
tags: [tooling, skills, snapshot]
---

# Skills Split Complete

**As of 2026-09-12**

The Kovanica Blockchain Developer skill pack was split from a single monolithic `SKILL.md` into per-skill files.

## Structure

```
skills/
├── README.md                              # Skills index
├── kovanica-blockchain-developer/
│   └── SKILL.md                           # Entry point + overview
├── rfcs-index/
│   └── SKILL.md
├── rfc-001-multisig/
│   └── SKILL.md
├── rfc-002-multi-asset/
│   └── SKILL.md
├── rfc-003-stealth-script/
│   └── SKILL.md
├── rfc-004-htlc/
│   └── SKILL.md
├── rfc-005-vault/
│   └── SKILL.md
├── rfc-006-tokenomics/
│   └── SKILL.md
├── rfc-006-activation/
│   └── SKILL.md
├── emission-math/
│   └── SKILL.md
├── api-reference/
│   └── SKILL.md
├── ghostdag-notes/
│   └── SKILL.md
├── operator-matrix/
│   └── SKILL.md
├── node-ops/
│   └── SKILL.md
├── project-planning/
│   └── SKILL.md
├── rust-client-notes/
│   └── SKILL.md
├── mainnet-checklist/
│   └── SKILL.md
├── faq-pitfalls/
│   └── SKILL.md
├── cheat-sheet/
│   └── SKILL.md
└── scripts/
    └── SKILL.md
```

20 skill folders total. Each contains a single `SKILL.md` file.

## Vault (agent brain)

```
markdown-vault/
├── README.md
├── Markdown.kov.md              # Vault index + cross-reference map
├── Memory/
│   ├── current-branch-state.md
│   ├── rfc-006-tokenomics-numbers.md
│   └── kovanica-tool-surface.md
├── Chats/
├── Tasks/
└── Notes/
    ├── code-samples/README.md
    └── snapshots/upgrade-progress-2026-09-12.md
```

## Cross-reference

- `skills/README.md` — skills index
- `markdown-vault/Markdown.kov.md` — vault index
- `markdown-vault/Memory/kovanica-tool-surface.md` — Kovanica tool inventory
- `markdown-vault/Notes/snapshots/upgrade-progress-2026-09-12.md` — this session's snapshot
