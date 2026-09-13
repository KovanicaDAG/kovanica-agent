# Upgrade Progress — Kovanica + Obsidian-Vault Integration

> Snapshot: 2026-09-12
> Scope: Skill pack split (done earlier today) + MARKDOWN.god/Obsidian-Vault extraction (this session)

---

## What was done earlier today (before this session)

1. **Skill pack split** — monolithic `SKILL.md` (1374 lines, 56KB) split into 20 per-skill files under `skills/<skill-name>/SKILL.md`. Entry point at `skills/kovanica-blockchain-developer/SKILL.md`. Index at `skills/README.md`.

2. **Vault structure created** — `markdown-vault/` with README, Markdown.kov.md index, Memory/ (4 notes), Chats/, Tasks/, Notes/ (code-samples/, snapshots/).

3. **Vault memory written** — current-branch-state.md, rfc-006-tokenomics-numbers.md, kovanica-tool-surface.md, skills-split-complete.md.

4. **Code samples vault** — `Notes/code-samples/README.md` with indexed snippets (RFC-006 helpers, Ed25519 signing, tools_ext.py, repl.py, sandbox, vault wiring).

5. **Bidirectional links** — SKILL.md → skills/ + markdown-vault/, skills/README.md → all skills + vault, markdown-vault/Markdown.kov.md → cross-reference table.

---

## What was done in this session (Obsidian-Vault extraction)

### Sources inspected

- `/root/Obsidian-Vault/agents/MARKDOWN.god` — 2696 lines, compiled 2026-08-26 22:24 UTC, 40 documents
- `/root/Obsidian-Vault/MARKDOWN.god/MARKDOWN.god` — 2743 lines, compiled 2026-08-25 21:28 UTC, 41 documents
- `/root/Obsidian-Vault/agents/` — full registry: 12 subagents, 10 skills, 13 commands, 2 plugins, 3 templates, INDEX.md, WORKFLOWS.md, MIGRATION.md

### Vault memory notes written

1. `markdown-vault/Memory/MARKDOWN.god-extract.md` (18,768 bytes) — deepest extract:
   - The 7 Laws (Finish Line, Authority, Registry discipline, Determinism is sacred, Consensus changes demand proof, Never invent, Trackers Precede PRs)
   - Agent prompt structure (YAML frontmatter + markdown body + Finish Line block)
   - Best prompt patterns from each subagent (security-auditor, protocol-dev, code-reviewer, test-engineer, migration-engineer, devops-engineer, performance-engineer)
   - 6 multi-agent workflows (release, consensus change, performance, API evolution, migration, vault maintenance)
   - 10 skills with triggers and decision guides
   - 13 commands with agents and safety gates
   - 2 plugins (claude-code-tools, opencode-gemini-auth)
   - 3 templates (agent, command, skill)
   - 7 code samples (migration registry, SPV filter, finality checkpoint, security audit, fuzz targets, protocol dev commands, release checklist)
   - Setup patterns (env vars, build matrix, test stages, CI/CD, monitoring, infrastructure layout)

2. `markdown-vault/Memory/obsidian-vault-extract.md` (12,690 bytes) — broader extract:
   - Vault structure best practice (agents/, KovanicaDAG/, .obsidian/)
   - Agent registry pattern (INDEX.md brain map, YAML frontmatter, markdown body, Finish Line)
   - Command pattern (description, agent, body, $ARGUMENTS, safety gates, Finish Line)
   - Skill pattern (name, description with trigger keywords, trigger keywords, decision guide, checklist, compatibility rules, wire examples, commands, Finish Line)
   - Plugin pattern (local vs npm, tools table, usage, implementation)
   - Template pattern (agent/command/skill templates for reproducibility)
   - 7 code samples (same as above, adapted for Kovanica context)
   - 10 setup patterns (env vars, build matrix, test stages, CI/CD, monitoring, infrastructure, git workflow, versioning, release checklist)
   - Cross-reference to Kovanica (10 adoption points)

### Cross-reference updates

- `markdown-vault/Markdown.kov.md` — added rows for both new memory notes in cross-reference table
- `skills/README.md` — added reference to Obsidian-Vault extraction
- `SKILL.md` — banner updated to mention Obsidian-Vault extraction

---

## How Kovanica should adopt these patterns

1. **Finish Line invariant** — every agent prompt (skill, command, subagent) ends with the same "shipped vs edited" block
2. **Determinism is sacred** — hard rule in SYSTEM_PROMPT.md, not just a guideline
3. **Consensus changes demand proof** — written rationale + deterministic + adversarial tests
4. **Never invent** — verify before claiming; if not verifiable, say so
5. **Trackers Precede PRs** — check off TODO/ROADMAP before commit
6. **Agent registry** — `skills/<skill-name>/SKILL.md` with YAML frontmatter mirrors `agents/skills/`
7. **Command pattern** — `kovanica <subcommand>` mirrors `agents/commands/`
8. **Skill pattern** — trigger keywords + decision guide + checklist + wire examples
9. **Plugin pattern** — tools exposed as plugins (bash, edit, glob, grep, read, write, task)
10. **Hard-won lessons** — document invariants that must not break
11. **Doctor command** — health-check the agent registry
12. **Brain map** — `skills/README.md` mirrors `agents/INDEX.md`

---

## Obsidian-Vault structure (for reference)

```
/root/Obsidian-Vault/
├── agents/
│   ├── INDEX.md              # Brain map
│   ├── WORKFLOWS.md          # 6 multi-agent pipelines
│   ├── MIGRATION.md          # Migration notes
│   ├── agents/
│   │   ├── subagents/        # 12 subagents
│   │   ├── skills/           # 10 skills
│   │   ├── commands/         # 13 commands
│   │   ├── plugins/          # 2 plugins
│   │   ├── templates/        # 3 templates
│   │   ├── tools/            # Tool configs
│   │   └── tests/            # Validation tests
│   └── scripts/              # build-god-brain.sh, sync-agents.sh
├── KovanicaDAG/              # Project snapshots
│   ├── myObsidianVaultDAG.md
│   ├── CODE_INDEX.md
│   ├── ROADMAP.md
│   ├── AGENTS.md
│   └── kovanica-*/
└── .obsidian/                # gitignored
```

---

## Key differences: Obsidian-Vault vs Kovanica

| Aspect | Obsidian-Vault (MARKDOWN.god) | Kovanica (this repo) |
|--------|-------------------------------|------------------|
| Agent definitions | `agents/subagents/*.md` (12) | `skills/<skill-name>/SKILL.md` (20) |
| Commands | `agents/commands/*.md` (13) | `kovi` CLI subcommands |
| Skills | `agents/skills/*.md` (10) | `skills/<skill-name>/SKILL.md` (20) |
| Templates | `agents/templates/` (3) | Not yet present |
| Brain map | `agents/INDEX.md` | `skills/README.md` |
| Workflows | `agents/WORKFLOWS.md` (6 pipelines) | Not yet present |
| Vault | `markdown-vault/` (separate repo) | `markdown-vault/` (in this repo) |
| Sync | `scripts/sync-agents.sh` | Not yet present |
| Doctor | `doctor` command | Not yet present |

---

*Snapshot: 2026-09-12 — Kovanica skill pack split + Obsidian-Vault MARKDOWN.god extraction.*
