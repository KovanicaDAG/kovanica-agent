# MARKDOWN.god — Best Agent Logic Extract

> Extracted from `/root/Obsidian-Vault/agents/MARKDOWN.god` and `/root/Obsidian-Vault/MARKDOWN.god/MARKDOWN.god`
> (compiled 2026-08-25/26, 40–41 documents, KovanicaDAG agent fleet).
> This note captures the highest-signal patterns: laws, prompts, setup, skills, plugins, code samples.

---

## The Laws (override everything)

1. **Finish Line** — work is done when *shipped*, never when merely edited.
   - Vault edits → `git add -A && git commit -m "docs: <what>" && git push origin main`
   - Code edits → feature branch in `/root/kovanica-protocol`, gated by `cargo fmt --check && cargo clippy --all-targets && cargo test`, then draft PR.
   - Nothing changed? Say so explicitly and stop.

2. **Authority** — protocol/code truth lives in `/root/kovanica-protocol` (read its `AGENTS.md` first). Vault holds docs and snapshots; prefer the current merged layout over old snapshots when they disagree.

3. **Registry discipline** — edit agent definitions ONLY under `agents/` in the vault, never the synced copies (`~/.claude/*`, tool config dirs). After edits run sync script, validate with tests.

4. **Determinism is sacred** — consensus output is a pure function of the DAG. No HashMap order, wall-clock time, or unstable sorts in consensus paths. Tie-breaks fall back to BlockId byte order.

5. **Consensus changes demand proof** — written rationale naming protocol semantics plus deterministic AND adversarial tests (wide forks beyond k, Byzantine parents, tie-breaks, partitions).

6. **Never invent** — do not fabricate APIs, paths, commands, or roadmap items. Verify before claiming: run commands, don't assume output.

7. **Trackers Precede PRs** — always explicitly verify and check off completed items in TODO.md and ROADMAP.md *before* committing and opening a Draft PR.

---

## Agent prompt structure (from subagents)

Every subagent in the vault follows this template:

```yaml
description: <one-sentence role>
mode: subagent
permission:
  edit: allow | deny
  bash: allow | ask
```

Then markdown body:

```markdown
# <Agent Name> Agent

You are a specialized agent for <domain>.

## Responsibilities
- <primary>
- <secondary>

## Key Conventions (from AGENTS.md)
- <consensus correctness rules>
- <determinism rules>
- <testing rules>
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

**Key insight:** Every agent ends with the same Finish Line block. This is the invariant that makes the fleet coherent.

---

## Best prompt patterns extracted

### Security Auditor prompt (highest rigor)

Scope: crypto primitives (BLAKE3, SHA-256, Schnorr/Ed25519, VRF, HKDF, Noise), consensus safety (liveness, safety, finality, incentive compatibility, resource exhaustion), P2P/network security (peer auth, message validation, eclipse/partition resistance, replay protection, privacy), smart contract/script safety (future).

Audit methodology: STRIDE threat modeling → code review checklist (no unsafe, constant-time crypto, input validation, checked arithmetic, resource bounds, error handling, dependencies) → consensus-specific checks (determinism proof, k-cluster invariant, finality monotonicity, pruning correctness, VRF bias resistance).

Tools: `cargo audit`, `cargo deny`, `cargo fuzz`, `cargo clippy -D warnings`, `cargo geiger`, `cargo miri`.

### Protocol Dev prompt (most referenced)

Project structure: 4 crates (kovanica-dag, kovanica-state, kovanica-node, kovanica-cli) + web/ + docs/vault/.

Build/test: `cargo build`, `cargo test`, `cargo test <name>`, `cargo clippy --all-targets`, `cargo fmt`, `cargo run -p kovanica-node -- demo`.

Key conventions: consensus correctness demands written rationale + deterministic + adversarial tests; determinism = pure function of DAG; k-cluster invariant `blue_anticone_size <= k`; never commit to default branch; branch naming `consensus/...`, `dag/...`, `ledger/...`, `claude/<topic>`.

Hard-won lessons: SPV block filters must map 64-bit addresses to bounded interval before Golomb-Rice encoding; finality checkpointing must explicitly prune via `Block::new_pruned_with_vrf` so bytes match reconstructed block.

### Code Reviewer prompt (consensus gate)

Checklist priority: consensus-critical changes first (selected-parent, mergeset, k-cluster, blue score, linearization), then determinism, then adversarial tests, then style/lint, then security.

Response format: Summary → Blocking Issues (file:line + why) → Non-Blocking → Nitpicks.

### Test Engineer prompt (adversarial focus)

Test philosophy: consensus code requires adversarial tests, not just happy paths; property/invariant tests > example-based; determinism mandatory; test invariants, not implementation.

Key invariants: GHOSTDAG (k-cluster, selected-parent heaviest blue work, linearization total order, determinism, adversarial wide forks), reachability (differential vs naive walk, incremental == fresh), difficulty/PoW (enforcement, target determinism, Nakamoto arithmetic), ledger/state (double-spend across parallel blocks, order-independence, per-block == batch, snapshot round-trip, finality pruning), node/P2P (multi-node convergence, discovery/relay, TCP/WS, SPV/DHT).

### Migration Engineer prompt (safety-critical)

Migration types: store migrations (schema versioning, forward-only, batched, idempotent), protocol upgrades (soft fork vs hard fork, BIP9 or fixed height, testnet first), state transitions (genesis changes, checkpoint format, pruning policy).

Workflow: Assess → Design (RFC note in vault) → Implement (registry pattern) → Test (property test: migrate → snapshot → equals expected) → Dry run (production-sized snapshot) → Deploy (backup → stop → migrate → start → verify) → Document.

Safety rules: backup before every migration, never mutate during iteration, bound memory (10k keys max batches), feature-flag risky reads, two-phase hard fork, rollback plan required BEFORE deploying.

Registry pattern:
```rust
pub const MIGRATIONS: &[(u32, MigrationFn)] = &[
    (1, migrate_v0_to_v1),
    (2, migrate_v1_to_v2),
];
```

### DevOps Engineer prompt (infrastructure)

CI/CD: build matrix (Linux x86_64/aarch64, Windows, macOS), test stages (unit → integration → adversarial → property → fuzz), lint/format, security (`cargo audit`, `cargo deny`, `cargo geiger`), artifacts (static musl, Docker, SBOM), release (automated tagging, changelog, GitHub releases, crate publishing).

Monitoring: Prometheus + Grafana, structured JSON logging, OpenTelemetry tracing, Alertmanager → PagerDuty/Slack, dashboards for node health/consensus/P2P/mempool/RPC.

Key metrics to alert on: consensus height lag (>10 warn, >100 crit), peer count (<3 warn, 0 crit), sync status (syncing warn, stalled >10m crit), mempool size (>100k warn, >1M crit), RPC error rate (>1% warn, >5% crit), disk usage (>70% warn, >90% crit), memory usage (>80% warn, >95% crit), block processing time (>5s warn, >30s crit).

### Performance Engineer prompt (measurement-first)

Focus areas: consensus (block processing throughput, GHOSTDAG coloration latency, reachability oracle, memory usage, parallel validation), state/ledger (UTXO lookup/insertion, snapshot, pruning, batch apply), node/P2P (block propagation, mempool throughput, peer handling, sync speed, explorer query latency), web/UI (page load, API response, bundle size).

Benchmarking toolkit: `cargo bench` (criterion), custom benchmarks, `cargo flamegraph`, `heaptrack`, `perf record -g`.

Key metrics: block processing >10k blocks/s, UTXO lookup <1ms p99, block propagation <500ms p99 (LAN), sync speed >1M blocks/hr, mempool throughput >5k tx/s, RPC latency <50ms p99.

Optimization patterns: lock-free data structures (crossbeam, dashmap), batch operations, async/await correctly (`spawn_blocking`), memory pooling, SIMD (blake3, borsh), database tuning (sled/rocksdb compaction, cache sizing, bloom filters).

Rule: never optimize without a measurement proving the bottleneck. Micro-benchmarks lie about cache effects — validate with real node run.

---

## Multi-agent workflows (pipelines)

### Release Pipeline
```
test-engineer (run-tests + fuzz)
  → code-reviewer (final review gate)
    → security-auditor (/audit)
      → release-engineer (tag, build, changelog)
        → devops-engineer (deploy canary → full)
```
Gate: each stage must pass before next starts. Security Critical finding aborts pipeline.

### Consensus Change (highest scrutiny)
```
protocol-dev (RFC note in vault first)
  → doc-writer (spec diff published for review)
    → code-reviewer (consensus checklist)
      → security-auditor (invariant verification)
        → test-engineer (adversarial suite: wide forks, partitions, tie-breaks)
          → migration-engineer (activation plan if behavior changes)
            → devops-engineer (testnet soak 48h before mainnet)
```

### Performance Investigation
```
performance-engineer (/benchmark baseline)
  → performance-engineer (/profile bottleneck)
    → protocol-dev (implement fix on branch)
      → test-engineer (regression + determinism tests)
        → performance-engineer (/benchmark compare ≥10% win required)
          → code-reviewer (approve PR)
```

### API Evolution
```
api-designer (design + OpenAPI spec update)
  → code-reviewer (compat check — no breaking change without /v2)
    → protocol-dev (implementation)
      → test-engineer (integration tests vs spec)
        → api-designer (SDK regeneration + sunset headers)
```

### Store Migration
```
migration-engineer (/migrate plan <name>)
  → doc-writer (runbook update)
    → migration-engineer (/migrate dry-run on prod snapshot)
      → devops-engineer (backup verification + scheduled apply)
        → test-engineer (post-migrate deep verify + genesis-sync equivalence)
```

### Vault Maintenance (weekly)
```
vault-sync (/sync-vault)
  → protocol-dev (/reindex CODE_INDEX.md)
    → doc-writer (/update-roadmap)
      → vault-sync (commit + push, docs: prefix)
```

---

## Skills (10 total)

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `api-design` | API, endpoint, RPC, REST, GraphQL, WebSocket, OpenAPI, schema, SDK, breaking change | Design REST/GraphQL/WS/JSON-RPC APIs, OpenAPI spec, SDK generation, versioning |
| `code-review` | review, PR, pull request, consensus, safety, correctness | Review PRs for consensus safety, style, correctness |
| `doc-writer` | editing vault docs, CODE_INDEX, ROADMAP, AGENTS notes | Write and maintain vault documentation |
| `fuzzing` | fuzz, fuzzing, cargo-fuzz, crash, corpus, arbitrary, proptest | Fuzz deserialization, consensus inputs, parsers with cargo-fuzz |
| `migration` | migration, schema, upgrade, hard fork, soft fork, activation, backfill, rollback | Plan/execute store schema migrations and protocol upgrades |
| `profiling` | benchmark, profile, flamegraph, throughput, latency, bottleneck, optimize, perf, criterion | Benchmark and profile hot paths |
| `protocol-dev` | working on crates, consensus code, build/test commands | Assist with kovanica-protocol development |
| `security-audit` | security, audit, vulnerability, CVE, exploit, DoS, attack, threat, secrets | Audit crypto, consensus, input handling for vulnerabilities |
| `testing` | test, adversarial, property, invariant, consensus, k-cluster, reachability | Write/run adversarial tests, property tests, consensus invariants |
| `vault-sync` | syncing docs, updating CODE_INDEX, pushing vault changes | Sync docs between kovanica-protocol and vault snapshots |

---

## Commands (13 total)

| Command | Agent | Description |
|---------|-------|-------------|
| `/audit` | security-auditor | Run security audit (deps, unsafe, secrets, clippy) |
| `/benchmark` | performance-engineer | Run criterion benchmarks + compare against baseline |
| `/checkpoint` | vault-sync | Create milestone/checkpoint in vault |
| `/deploy` | release-engineer | Deploy to testnet (requires DEPLOY_ENABLED) |
| `/doctor` | vault-sync | Health-check agent registry (symlinks, configs, drift) |
| `/fuzz` | test-engineer | Run cargo-fuzz targets for input-parsing hardening |
| `/lint` | code-reviewer | Run `cargo fmt --check && cargo clippy --all-targets` |
| `/migrate` | migration-engineer | Plan/execute store migration or protocol upgrade |
| `/profile` | performance-engineer | Profile with flamegraph or perf |
| `/reindex` | protocol-dev | Rebuild CODE_INDEX.md from source tree |
| `/run-tests` | test-engineer | Run `cargo test` with filters |
| `/sync-vault` | vault-sync | Sync vault snapshots from kovanica-protocol |
| `/update-roadmap` | doc-writer | Update ROADMAP.md with stage progress |

---

## Plugins (2 total)

### claude-code-tools (local)
Exposes Claude Code's built-in tools as OpenCode-compatible plugins:
- `bash`, `edit`, `glob`, `grep`, `read`, `write`, `task`, `webfetch`, `websearch`

Usage: reference in `opencode.json` as `"./agents/plugins/claude-code-tools.ts"`.

### opencode-gemini-auth (npm)
Gemini API authentication for OpenCode. Install: `npm install -g opencode-gemini-auth`. Configure in `opencode.json` with `GEMINI_API_KEY` env var.

---

## Templates (reproduce the brain)

### Agent template
```yaml
description: <one sentence>
mode: subagent
permission:
  edit: allow | deny
  bash: allow | ask
```
Body: responsibilities, context (project/repo/key files), guidelines (follow AGENTS.md, don't invent, run tests), commands, references.

### Command template
```yaml
description: One sentence
agent: <agent-name>
```
Body: command body with `$ARGUMENTS` for user input.

### Skill template
```yaml
name: <skill-name>
description: One sentence covering what + when to trigger. Front-load trigger keywords.
```
Body: trigger keywords, sections with instructions/patterns/examples, commands.

---

## Code samples (highest value)

### Rust migration registry pattern
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
            migrate(db)?;               // idempotent, batched
            set_version(db, version)?;
        }
    }
    Ok(target)
}
```

### SPV filter encoding (hard-won lesson)
When encoding 64-bit addresses into Golomb-Rice filter, must map to bounded interval (`N * 2^k`) first — never push raw 64-bit difference as unary 1s.

### Finality checkpointing (hard-won lesson)
When writing checkpoint block's payload, must explicitly prune via `Block::new_pruned_with_vrf` so bytes match reconstructed block from `read_checkpoint`.

### Consensus test invariants
- `blue_anticone_size <= k` for every blue block (k-cluster invariant)
- Selected parent is always the tip with heaviest blue work
- Linearization is a total order consistent with partial order
- Deterministic: identical DAG → identical linearization
- Adversarial: wide forks beyond k, equivocating parents, partition heals

### Security audit quick checks
```bash
cargo audit
cargo deny check advisories bans licenses sources
cargo clippy --all-targets -- -D warnings
grep -rn "unsafe" crates/ | grep -v test
grep -rniE "(api[_-]?key|secret|password)\s*=" crates/ --include="*.rs" | grep -v test
```

### Fuzz targets (priority order)
1. `block_decode` — `Block::decode(&[u8])` — High
2. `tx_decode` — `Transaction::decode(&[u8])` — High
3. `vrf_verify` — `VrfProof::verify(bytes)` — High
4. `wire_message` — P2P message framing — High
5. `filter_decode` — SPV Golomb-Rice filter read — Medium
6. `config_parse` — node config loader — Low

Rules: no panics allowed (target must return Result), bound work per input (reject oversized early), seed corpus (commit valid fixtures), dictionary helps (magic bytes, opcodes), determinism check inside target (decode twice, assert equal).

### Vault sync recipe
```bash
# 1. Make edits under KovanicaDAG/
# 2. Commit
git add -A && git commit -m "docs: <what changed>"
# 3. If push rejected
git pull --rebase origin main
# 4. Push
git push origin main
```

---

## Setup / configuration patterns

### Environment
- `KOVANICA_POW=1`, `KOVANICA_MINE=0`, `KOVANICA_MINE_SECS=120`, `KOVANICA_FAUCET=0`, `KOVANICA_ALLOW_RESET=0`, `KOVANICA_OPERATOR=0`, `KOVANICA_LISTEN=0.0.0.0:9000`, `KOVANICA_PEERS=seed.kovanica.online:9000`, `KOVANICA_DATA=$PWD/data`

### Build matrix
- Linux (x86_64, aarch64), Windows, macOS
- Static musl binaries: `cargo build --release --target x86_64-unknown-linux-musl`
- Docker: multi-stage, distroless, `ghcr.io/kovanica/node:tag`

### Test stages
unit → integration → adversarial → property → fuzz

### Git workflow
- Never commit to default branch directly
- Feature branch + draft PR
- Branch naming: short, kebab-case, scoped — `consensus/...`, `dag/...`, `ledger/...`, `claude/<topic>`
- Run `cargo fmt`, `cargo clippy --all-targets`, `cargo test` before pushing
- Commit subjects: imperative, prefixed `docs:` for vault, `feat:`/`fix:`/`refactor:`/`test:`/`chore:` for code

### Versioning
- SemVer: MAJOR (consensus-breaking), MINOR (new features/protocol upgrades), PATCH (bug fixes/non-consensus)
- Changelog: conventional commits → `git-cliff` / `cargo-release`
- Binaries: `cargo-dist` for multi-platform, signed checksums, SBOM (SPDX)

---

## Cross-reference to Kovanica vault

The Kovanica agent at `/root/kovanica-agent` should adopt these MARKDOWN.god patterns:

1. **Finish Line** as the invariant closing block in every agent prompt
2. **Determinism is sacred** as a hard rule in SYSTEM_PROMPT.md
3. **Consensus changes demand proof** — written rationale + deterministic + adversarial tests
4. **Never invent** — verify before claiming
5. **Trackers Precede PRs** — check off TODO/ROADMAP before commit

Vault structure parallels:
- MARKDOWN.god `agents/subagents/` ↔ Kovanica `skills/<skill-name>/SKILL.md`
- MARKDOWN.god `agents/commands/` ↔ Kovanica CLI subcommands
- MARKDOWN.god `agents/skills/` ↔ Kovanica skill definitions
- MARKDOWN.god `markdown-vault/Memory/` ↔ Kovanica `markdown-vault/Memory/`

---

*Extracted 2026-09-12 from MARKDOWN.god (compiled 2026-08-25/26, 40–41 documents).*
