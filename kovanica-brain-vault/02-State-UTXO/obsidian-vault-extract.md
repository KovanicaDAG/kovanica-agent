# Obsidian-Vault — Best Patterns Extract

> Extracted from `/root/Obsidian-Vault/` (agent fleet registry, 40+ documents, compiled 2026-08-25/26).
> This note captures the best agent logic, prompt patterns, setup, skills, plugins, and code samples
> from the MARKDOWN.god brain, adapted for Kovanica at `/root/kovanica-agent`.

---

## Vault structure (best practice)

```
Obsidian-Vault/
├── agents/
│   ├── INDEX.md                    # Brain map — what's where
│   ├── WORKFLOWS.md                # Multi-agent pipeline compositions
│   ├── MIGRATION.md                # Migration notes
│   ├── agents/                     # Agent definitions (edit here only)
│   │   ├── subagents/              # 12 subagents (api-designer, code-reviewer, etc.)
│   │   ├── skills/                 # 10 skills (api-design, fuzzing, etc.)
│   │   ├── commands/               # 13 commands (/audit, /benchmark, etc.)
│   │   ├── plugins/                # 2 plugins (claude-code-tools, gemini-auth)
│   │   ├── templates/              # 3 templates (agent, command, skill)
│   │   ├── tools/                  # Tool configs (opencode.json, etc.)
│   │   └── tests/                  # Validation tests
│   └── scripts/                    # build-god-brain.sh, sync-agents.sh
├── KovanicaDAG/                    # Project snapshots (CODE_INDEX, ROADMAP, AGENTS, etc.)
├── .obsidian/                      # App state — gitignored
└── .gitignore
```

Key rules:
- Edit agent definitions ONLY under `agents/` — never the synced copies
- After edits: run `./scripts/sync-agents.sh`, validate with `./agents/tests/run-tests.sh`
- Commit subjects: imperative, prefixed `docs:` for vault, `feat:`/`fix:` for code
- Git: feature branch + draft PR, never default branch

---

## Agent registry pattern (best from MARKDOWN.god)

### INDEX.md brain map
```
Part  | Section                        | Docs
------|--------------------------------|------
I     | Multi-Agent Workflows          | 1
II    | Subagents                      | 12
III   | Skills                         | 10
IV    | Commands                       | 13
V     | Plugins                        | 2
VI    | Templates (reproduce the brain)| 3
```

### Subagent YAML frontmatter
```yaml
description: <one-sentence role>
mode: subagent
permission:
  edit: allow | deny
  bash: allow | ask
```

### Subagent markdown body
```markdown
# <Agent Name> Agent

You are a specialized agent for <domain>.

## Responsibilities
- <primary>
- <secondary>

## Key Conventions (from AGENTS.md)
- <consensus correctness>
- <determinism>
- <testing>
- <git workflow>

## Commands
```bash
cargo test <filter>
cargo fmt --check
cargo clippy --all-targets
```

## Finish Line
A task is not done when the files are edited — it is done when the work is shipped.
- Vault edits: git add/commit/push
- Code edits: feature branch + gates + draft PR
- No files changed? Nothing to commit — say so explicitly and stop.
```

---

## Command pattern (best from MARKDOWN.god)

```yaml
description: One sentence describing what the command does
agent: <agent-name>
```

Body:
- Command body (bash or prompt)
- Use `$ARGUMENTS` for user input
- Describe `$ARGUMENTS` — optional/required, format
- Safety gates if needed (confirmation before destructive action)
- Finish Line block

Example (`/migrate`):
```yaml
description: Plan or execute a store migration / protocol upgrade
agent: migration-engineer
```

Body includes: mode from `$ARGUMENTS` (`plan <name>` | `dry-run` | `apply`), safety gates before `apply` (backup exists, dry-run completed, rollback documented, user confirmed), Finish Line.

---

## Skill pattern (best from MARKDOWN.god)

```yaml
name: <skill-name>
description: One sentence covering what this skill does AND when to trigger it. Front-load trigger keywords.
```

Body:
- Trigger keywords (comma-separated)
- Decision guide (table: need → choose)
- Checklist (numbered steps)
- Compatibility rules
- Wire examples
- Commands
- Finish Line

Example (`api-design` skill): trigger keywords `API, endpoint, RPC, REST, GraphQL, WebSocket, OpenAPI, schema, SDK, breaking change`, decision guide table (simple CRUD → REST, complex nested → GraphQL, push updates → WS, control plane → JSON-RPC), checklist for adding endpoint (1. privacy leak? 2. resource-oriented name 3. pagination 4. RFC 7807 errors 5. OpenAPI spec 6. SDK regeneration 7. version if breaking), compatibility rules (adding optional field safe, removing/retyping breaking, breaking needs /v2 + 6-month sunset), wire examples (REST JSON, WS subscribe/unsubscribe).

---

## Plugin pattern (best from MARKDOWN.god)

### Local plugin (claude-code-tools)
```yaml
name: claude-code-tools
source: local
description: Claude Code tool integrations (bash, edit, glob, grep, task, etc.)
```

Body: tools available table (bash, edit, glob, grep, read, write, task, webfetch, websearch), usage (reference in opencode.json), implementation note (create .ts exporting plugin that wraps Claude Code tool definitions).

### npm plugin (opencode-gemini-auth)
```yaml
name: opencode-gemini-auth
source: npm
description: Gemini authentication for OpenCode
```

Body: installation (`npm install -g opencode-gemini-auth`), configuration (add to opencode.json with `GEMINI_API_KEY` env var), usage (select gemini/ models in model picker).

---

## Template pattern (reproduce the brain)

### Agent template
```yaml
description: <What this agent does — one sentence>
mode: subagent
permission:
  edit: allow
  bash: ask
```
Body: responsibilities, context (project/repo/key files), guidelines (follow AGENTS.md, don't invent, run tests), commands, references.

### Command template
```yaml
description: One sentence describing what the command does
agent: <agent-name>
```
Body: command body with `$ARGUMENTS`, `$1`, `$2` for positional args.

### Skill template
```yaml
name: <skill-name>
description: One sentence covering what this skill does AND when to trigger it. Front-load trigger keywords.
```
Body: trigger keywords, sections with instructions/patterns/examples, commands.

---

## Code samples (best from MARKDOWN.god)

### Migration registry (Rust)
```rust
pub const MIGRATIONS: &[(u32, MigrationFn)] = &[
    (1, migrate_v0_to_v1),
    (2, migrate_v1_to_v2),
    (3, migrate_v2_to_v3),
];

pub fn run_migrations(db: &Db) -> Result<u32> {
    let current = current_version(db)?;
    let target = MIGRATIONS.last().map(|(v, _)| *v).unwrap_or(current);
    if current == target { return Ok(current); }
    for &(version, migrate) in MIGRATIONS {
        if version > current {
            info!(version, "applying migration");
            migrate(db)?;
            set_version(db, version)?;
        }
    }
    Ok(target)
}
```

### SPV filter encoding (hard-won lesson)
```rust
// When encoding 64-bit addresses into Golomb-Rice filter:
// MUST map to bounded interval (N * 2^k) first
// NEVER push raw 64-bit difference as unary 1s
```

### Finality checkpointing (hard-won lesson)
```rust
// When writing checkpoint block's payload:
// MUST explicitly prune via Block::new_pruned_with_vrf
// so bytes match reconstructed block from read_checkpoint
```

### Security audit quick checks
```bash
cargo audit
cargo deny check advisories bans licenses sources
cargo clippy --all-targets -- -D warnings
grep -rn "unsafe" crates/ | grep -v test
grep -rniE "(api[_-]?key|secret|password)\s*=" crates/ --include="*.rs" | grep -v test
```

### Fuzz targets (priority order)
| Target | Entry point | Priority |
|--------|-------------|----------|
| `block_decode` | `Block::decode(&[u8])` | High |
| `tx_decode` | `Transaction::decode(&[u8])` | High |
| `vrf_verify` | `VrfProof::verify(bytes)` | High |
| `wire_message` | P2P message framing | High |
| `filter_decode` | SPV Golomb-Rice filter read | Medium |
| `config_parse` | node config loader | Low |

Rules: no panics (target returns Result), bound work per input (reject oversized early), seed corpus (commit valid fixtures), dictionary helps (magic bytes, opcodes), determinism check inside target (decode twice, assert equal).

### Protocol dev commands
```bash
cargo build
cargo test                    # all
cargo test <name>            # single (e.g., adversarial_wide_fork)
cargo clippy --all-targets   # lint
cargo fmt                    # format (CI: cargo fmt --check)
cargo run -p kovanica-node -- demo  # run node
```

### Release checklist
- [ ] `cargo fmt --check` passes
- [ ] `cargo clippy --all-targets` warning-clean
- [ ] `cargo test` passes (all crates)
- [ ] `cargo build --release` succeeds
- [ ] CHANGELOG.md updated
- [ ] Cargo.toml versions bumped
- [ ] Git tag created: `v<version>`
- [ ] GitHub Release published with artifacts

---

## Setup patterns (best from Obsidian-Vault)

### Environment (participant node)
```bash
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

### Build matrix
- Linux (x86_64, aarch64), Windows, macOS
- Static musl: `cargo build --release --target x86_64-unknown-linux-musl`
- Docker: multi-stage, distroless, `ghcr.io/kovanica/node:tag`
- One-click install: `curl -sSfL https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.sh | bash`

### Test stages
unit → integration → adversarial → property → fuzz

### CI/CD tooling
- Build matrix: Linux (x86_64, aarch64), Windows, macOS
- Test stages: unit → integration → adversarial → property → fuzz
- Lint/format: `cargo fmt --check`, `cargo clippy --all-targets -D warnings`
- Security: `cargo audit`, `cargo deny`, `cargo geiger`
- Artifacts: Release binaries (static musl), Docker images, SBOM
- Release: Automated tagging, changelog, GitHub releases, crate publishing

### Monitoring stack
- Metrics: Prometheus + Grafana (node, consensus, P2P, mempool, RPC)
- Logging: Structured JSON (tracing), Loki aggregation
- Tracing: OpenTelemetry, distributed traces
- Alerting: Alertmanager → PagerDuty/Slack

### Infrastructure layout
```
/infra
├── ansible/
│   ├── inventory/
│   │   ├── testnet.yml
│   │   └── mainnet.yml
│   ├── roles/
│   │   ├── kovanica-node/
│   │   ├── prometheus/
│   │   ├── grafana/
│   │   └── loki/
│   └── playbooks/
│       ├── deploy.yml
│       ├── upgrade.yml
│       └── backup.yml
├── terraform/
│   ├── modules/
│   │   ├── testnet-cluster/
│   │   ├── monitoring/
│   │   └── dns-seeds/
│   ├── environments/
│   │   ├── testnet/
│   │   └── mainnet/
│   └── main.tf
└── docker/
    ├── Dockerfile.node
    ├── Dockerfile.explorer
    └── docker-compose.monitoring.yml
```

---

## Cross-reference to Kovanica

The Kovanica agent (`/root/kovanica-agent`) should adopt:

1. **Agent registry pattern** — `skills/<skill-name>/SKILL.md` mirrors `agents/skills/<skill>.md`
2. **Command pattern** — `kovanica <subcommand>` mirrors `agents/commands/<command>.md`
3. **YAML frontmatter** — every skill/command uses `name:`, `description:` frontmatter
4. **Finish Line invariant** — every agent prompt ends with the same shipped-vs-edited block
5. **Template system** — agent/command/skill templates for reproducibility
6. **Brain map** — `skills/README.md` mirrors `agents/INDEX.md`
7. **Workflow pipelines** — multi-agent compositions for release, consensus change, performance, API evolution, migration, vault maintenance
8. **Plugin pattern** — tools exposed as plugins (bash, edit, glob, grep, read, write, task)
9. **Hard-won lessons** — document invariants that must not break (like SPV filter encoding, finality checkpointing)
10. **Doctor command** — health-check the agent registry across all tools

Vault structure parallels:
- Obsidian-Vault `agents/subagents/` ↔ Kovanica `skills/<skill-name>/SKILL.md`
- Obsidian-Vault `agents/commands/` ↔ Kovanica CLI subcommands (`kovanica chat`, `kovanica grep`, etc.)
- Obsidian-Vault `agents/skills/` ↔ Kovanica skill definitions
- Obsidian-Vault `agents/templates/` ↔ Kovanica should have agent/command/skill templates
- Obsidian-Vault `markdown-vault/` ↔ Kovanica `markdown-vault/`

---

*Extracted 2026-09-12 from /root/Obsidian-Vault/ (MARKDOWN.god brain, 40–41 documents).*
