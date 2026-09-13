---
key: current-branch-state
value: "Checkout on tokenomics/rfc-006-emission-curve. RFC-006 steps 1-4 landed + green (785 tests). Steps 5-6 (treasury genesis + mainnet profile) and step 7 (supply accounting) pending. Branch has uncommitted work: node.rs + ledger.rs coinbase maturity fixes, expanded tokenomics.rs test suite. Remote origin only (no guthu remote yet)."
role: dev
learned_at: 2026-09-12T00:00:00+00:00
source: AGENTS.md + KOVANICA.md
tags: [rfcs, tokenomics, branch-state, snapshot]
---

# Current Branch State

**As of 2026-09-12**

- Branch: `tokenomics/rfc-006-emission-curve`
- RFC-006 steps 1–4: **LANDED** (emission curve, MAX_SUPPLY, coinbase maturity, fee burn) — 785 tests green
- RFC-006 steps 5–6: **PENDING** (treasury genesis + mainnet profile)
- RFC-006 step 7: **PENDING** (supply accounting / observability)
- Uncommitted changes: `node.rs`, `ledger.rs` (apply_dag tracks per-block chain height separately from blue score), expanded `tests/tokenomics.rs`
- Remotes: only `origin` = `https://github.com/KovanicaDAG/kovanica-protocol.git` — no `guthu` remote configured yet

## Key numbers (RFC-006)

| Constant | Value |
|----------|-------|
| ATOM | 100_000_000 |
| S0 (genesis subsidy) | 10 KVNC / block = 1_000_000_000 atoms |
| ERA_LENGTH | 2_000_000 blocks |
| α (decay) | 3/4 per era |
| MAX_SUPPLY | 90.2M KVNC = 90_200_000_000_000_000 atoms |
| COINBASE_MATURITY | 100 blocks |
| Premine | 0.2M KVNC |
| Treasury | 10M KVNC (10 × 1M vault tranches) |
| Curve total | 80M KVNC |
| Fee split | 75% burned / 25% producer |
| Fee floor | max(1, subsidy/500_000) atoms/byte |
| GHOSTDAG k | 3 |

## Cross-reference

- `skills/rfc-006-tokenomics/SKILL.md` — full spec
- `skills/emission-math/SKILL.md` — subsidy_at, fee_floor helpers
- `skills/rfc-006-activation/SKILL.md` — activation playbook, testnet reset
- `agent/tools_ext.py` — shared tool implementations
- `agent/repl.py` — REPL with vault memory wiring
