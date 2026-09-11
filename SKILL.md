# Kovanica Blockchain Developer — Complete Skill Pack

> Single-file export of the full skill for use with any agent.
> Generated for offline / cross-agent use. Prefer live /api/head values over any cached numbers.

---

## Table of contents

1. [SKILL.md (entry point)](#skillmd-entry-point)
2. [RFCs index](#rfcs--kvp-standards)
3. [RFC-001 Multisig](#rfc-001--kvp-101--multisig)
4. [RFC-002 Multi-asset](#rfc-002--kvp-102--native-multi-asset-tokens)
5. [RFC-003 Stealth + script](#rfc-003--kvp-103--stealth--script-v2)
6. [RFC-004 HTLC](#rfc-004--kvp-104--htlc-atomic-swaps)
7. [RFC-005 Vaults](#rfc-005--kvp-105--time-lock-vault--csv)
8. [RFC-006 Tokenomics](#rfc-006-tokenomics)
9. [RFC-006 Activation](#rfc-006-activation--testnet-reset-playbook)
10. [Emission math](#emission-math-rfc-006)
11. [API reference](#kovanica-http-api-reference)
12. [GHOSTDAG notes](#ghostdag-notes-for-kovanica-k3)
13. [Operator matrix](#operator-vs-participant-matrix)
14. [Node ops](#kovanica-node-operations)
15. [Project plan](#kovanica-project-planning-playbook)
16. [Rust client notes](#rust-client-notes-for-kovanica)
17. [Mainnet checklist](#mainnet-readiness-checklist)
18. [FAQ & pitfalls](#faq--common-pitfalls)
19. [Cheat sheet](#kovanica-cheat-sheet)
20. [Scripts](#scripts)

---

# SKILL.md (entry point)

```
name: kovanica-blockchain-developer

# Kovanica Blockchain Developer

Specialize in the Kovanica Protocol (KovanicaDAG) — a Rust-based GHOSTDAG BlockDAG with UTXO ledger and Ed25519 signatures. Native token **KVNC** (8 decimals). Current public network is testnet `kovanica-testnet`.

**Shipped RFCs / KVP standards** (see `references/rfcs-index.md`):
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

**Load full details from `references/tokenomics.md`.**

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
- `references/rfcs-index.md` — status table for RFC-001…006 / KVP-101…105
- `references/rfc-001-multisig.md` — KVP-101 M-of-N P2SH
- `references/rfc-002-multi-asset.md` — KVP-102 native multi-asset tokens
- `references/rfc-003-stealth-script.md` — KVP-103 stealth + script v2
- `references/rfc-004-htlc.md` — KVP-104 HTLC atomic swaps
- `references/vaults-rfc005.md` — KVP-105 time-lock vault + CSV (treasury & escrow)
- `references/tokenomics.md` — full RFC-006 (emission, cap, maturity, fees, treasury)
- `references/rfc-006-activation.md` — migration playbook, testnet-reset impact

**Core protocol & ops**
- `references/emission-math.md` — subsidy_at, fee floor, maturity helpers + constants
- `references/api.md` — endpoint table, pre/post-RFC-006 /api/head shapes, new ledger errors
- `references/ghostdag-notes.md` — k=3 implications, blue work, parallel minting vs hard cap
- `references/operator-matrix.md` — safe flag sets for home / explorer / seed / miner roles
- `references/node-ops.md` — env vars, seed vs clone, build & verification
- `references/project-plan.md` — layered decomposition, phase sequencing, risk register
- `references/rust-client-notes.md` — Ed25519 signing, client skeleton, post-RFC-006 checklist

**Ops, planning & quick ref**
- `references/mainnet-checklist.md` — go/no-go checklist before mainnet
- `references/faq-pitfalls.md` — common mistakes and answers
- `references/cheat-sheet.md` — one-page constants, commands, URLs

**Scripts**
- `scripts/check-head.sh` — local vs public head comparison
- `scripts/emission.rs` — self-contained Rust binary for subsidy / fee-floor at any height

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

When the user asks for code, configs, or plans, produce concrete Rust, shell, or API examples that match the current KovanicaDAG design (and the RFC-006 model once activated). Point to the reference files above when more detail is needed.```

*(Full frontmatter + body is in the original SKILL.md inside the skill folder.)*

---


------------------------------------------------------------

# Kovanica RFCs / KVP Standards — Implemented Set

Source of truth for status: https://kovanica.online/roadmap  
(KVP-101…105 = public names; RFC-00x = internal design docs)

| ID | Public name | Title | Status |
|----|-------------|-------|--------|
| RFC-001 | KVP-101 | Multisig (M-of-N P2SH) | **Shipped** |
| RFC-002 | KVP-102 | Native multi-asset tokens | **Shipped** |
| RFC-003 | KVP-103 | Stealth + script v2 | **Shipped** |
| RFC-004 | KVP-104 | HTLC atomic swaps | **Shipped** |
| RFC-005 | KVP-105 | Time-lock vault + CSV | **Shipped** |
| RFC-006 | — | Tokenomics (emission, cap, maturity, fee burn) | **Partial** (steps 1–4 landed) |

Detailed notes for each live in the files listed below. Always prefer the roadmap and the monorepo `docs/` when they diverge from this skill.

## Quick guidance when coding

- Multisig flows → RFC-001
- Issuing or transferring non-KVNC assets → RFC-002
- One-time / stealth addresses or advanced scripts → RFC-003
- Cross-party atomic swaps → RFC-004
- Time-locked vaults, treasury, escrow → RFC-005
- Supply, subsidy, fees, maturity → RFC-006

## Related client surfaces (from roadmap)

- Web explorer + browser wallet — Shipped
- Web KVP-102 UX (AssetPicker) — In progress (needs `asset_id` on HTTP API)
- Android APK + iOS IPA — Shipped
- Mobile light-node + UniFFI — Shipped
- Node HTTP `asset_id` exposure — Queued
- Token staking & sortition on KVP-102 assets — Queued
- Mainnet readiness — Tracked

------------------------------------------------------------

# RFC-001 / KVP-101 — Multisig (M-of-N P2SH)

**Status:** Shipped  
**Surfaces:** node + FFI + web multisig UI

## Summary

Threshold redeem scripts (M-of-N) using P2SH-style addresses.  
Supports spend proposals, collection of partial signatures, and combination into a final redeem transaction.

## Key behaviours

- Address derivation from a set of public keys + threshold M.
- Proposal creation that locks the intended outputs and sighash domain.
- Partial signature collection (each cosigner signs the same sighash offline).
- Combination / finalisation once ≥ M valid signatures are present.
- Activation gating so the feature can be consensus-enabled cleanly.

## Client rules

1. Never send private keys to the node.
2. Each cosigner must see the identical sighash before signing.
3. Prefer the official web multisig UI or CLI for production flows until custom tooling is audited.
4. After RFC-006 activation the normal fee-floor and maturity rules still apply to multisig spends.

## See also

- Roadmap entry: KVP-101
- Web surface: /multisig on the explorer/wallet apps

------------------------------------------------------------

# RFC-002 / KVP-102 — Native multi-asset tokens

**Status:** Shipped (core ledger)  
**Public name:** KVP-102 (native multi-asset; **not** an ERC-20)

## Summary

Multi-asset UTXOs with per-asset conservation.  
Coinbase can mint new asset types. Checkpoint format bumped (v4) to carry asset metadata.

## Key behaviours

- Every UTXO carries an `asset_id` (native KVNC is a distinguished id).
- Value conservation is enforced **per asset**.
- Coinbase outputs may mint a new asset or increase supply of an existing one under consensus rules.
- HTTP API exposure of `asset_id` on utxos / history / prepare is still being completed (roadmap “Node HTTP asset_id”).

## Client rules

1. Always treat balances as (asset_id → amount) maps, never a single scalar.
2. `prepare` / `submit` must preserve asset_id on every input and output.
3. Until the HTTP API fully surfaces `asset_id`, the web AssetPicker remains limited.
4. Explorers should badge non-KVNC assets distinctly.

## Open follow-ups (roadmap)

- Full web KVP-102 UX (AssetPicker)
- Token staking & sortition denominated in any KVP-102 asset
- Stable `asset_id` fields on all relevant HTTP endpoints

------------------------------------------------------------

# RFC-003 / KVP-103 — Stealth + script v2

**Status:** Shipped

## Summary

- One-time (stealth) keys via ECDH
- View tags for efficient scanning
- Bounded script machine supporting CLTV / CSV / hash-lock opcodes

## Key behaviours

- Sender can create a one-time address that only the recipient (with view key) can recognise and spend.
- View tags let light clients skip most outputs while scanning.
- Script v2 is intentionally small and bounded — no unbounded loops; designed for the existing UTXO + Ed25519 model.

## Client rules

1. Stealth sends require the recipient’s public scan/view key.
2. Wallets that support stealth must implement the ECDH + view-tag scan path.
3. Any script that uses CLTV/CSV must be validated against the bounded machine; do not assume Bitcoin Script compatibility.
4. Hardware-wallet support for stealth is still evolving — confirm against current FFI.

## See also

- RFC-005 re-uses the CLTV/CSV primitives for vaults
- RFC-004 re-uses hash-lock for HTLCs

------------------------------------------------------------

# RFC-004 / KVP-104 — HTLC atomic swaps

**Status:** Shipped

## Summary

Hashed time-locked contracts with explicit redeem and refund paths, plus swap-session helpers.

## Key behaviours

- Lock funds to a payment hash (hash-lock) + absolute or relative timeout.
- **Redeem path:** reveal preimage before timeout → funds to claimer.
- **Refund path:** after timeout → funds return to original owner.
- Session helpers coordinate the off-chain exchange of hashes / preimages while the on-chain HTLC provides the safety net.

## Client rules

1. Never reuse a preimage across independent swaps.
2. Timeouts must be chosen with the current block rate and reorg depth (k=3) in mind.
3. Both parties should verify the on-chain HTLC script before considering the swap “locked”.
4. After RFC-006 the normal fee-floor and maturity rules apply to the funding and claim transactions.

## Composition

HTLCs are built on the script-v2 machine from RFC-003 (hash-lock + CLTV/CSV).

------------------------------------------------------------

# RFC-005 / KVP-105 — Time-lock vault + CSV

**Status:** Shipped  
RFC-005 provides a CLTV/CSV-style vault primitive (check-lock-time-verify / check-sequence-verify).  
RFC-006 re-uses it unchanged for the 10 M KVNC treasury. Also available for user escrow.
## VaultScript shape (conceptual)

```text
VaultScript {
  absolute_time: u64,   // block height (or timestamp-as-height) after which CLAIM is valid
  relative_delay: u64,  // currently 0 for treasury tranches
  beneficiary: PublicKey, // CLAIM path (after expiry)
  owner: PublicKey,       // RECOVER path (strictly before expiry)
}
```

## Treasury vesting schedule (RFC-006)

10 tranches × 1 M KVNC:

| Tranche k | absolute_time          | ≈ calendar (at 1 blk/s) |
|-----------|------------------------|-------------------------|
| 1         | 1 × 31_536_000         | ~1 year                 |
| 2         | 2 × 31_536_000         | ~2 years                |
| …         | …                      | …                       |
| 10        | 10 × 31_536_000        | ~10 years               |

- **CLAIM** (after `absolute_time`) → funds move to treasury beneficiary.
- **RECOVER** (strictly before `absolute_time`) → treasury governance can claw back / redirect.
- Keys are currently **placeholders** (deterministically derived). A real multi-party key ceremony is required before mainnet.

## Client / wallet rules

1. Display vault UTXOs distinctly (locked / unlockable / claimable).
2. Never attempt to spend a vault output with a normal pay-to-pubkey path.
3. For CLAIM: current height (or median time) must be ≥ `absolute_time`.
4. For RECOVER: current height must be < `absolute_time` and the owner key must sign.
5. Treasury tranches also carry the coinbase maturity flag; in practice the long absolute_time makes the 100-block maturity irrelevant.

## User-facing escrow

The same `VaultScript` primitive is available for ordinary users (escrow, time-locked savings, etc.). Wallets should expose a simple “lock until height / date” UI that constructs the identical script type.

## Safety

- Placeholder treasury keys must never be used on mainnet.
- Any tool that generates vaults must make the absolute_time and the two keys explicit in the UI and in any exported descriptor.
- After the RFC-006 testnet reset the treasury vaults will be re-created at the new genesis; old vault addresses disappear with the rest of the chain.

------------------------------------------------------------

# Kovanica Tokenomics — RFC-006

> **Status (as of the provided RFC):** consensus changes partially implemented on
> `tokenomics/rfc-006-emission-curve`. Steps 1–4 (smooth emission curve,
> `MAX_SUPPLY` hard cap, coinbase maturity, fee burn) are landed and green
> (785 tests). Steps 5–6 (treasury genesis + mainnet profile) and Step 7
> (supply accounting / observability) are pending. Full spec is this document.

## 1. Motivation & goals

1. **Predictable, capped supply.** Total native KVNC hard-capped below 100M.
2. **Long-tail, fair emission.** Smooth geometric decay per era (no abrupt halvings).
3. **Security budget.** Block rewards (subsidy + fee share) fund PoW and VRF-staked validation.
4. **Deflationary fee market.** Majority of every transaction fee is burned.

## 2. Units

- **1 KVNC = 10⁸ atoms** (`ATOM = 100_000_000`).
- All consensus amounts are `u64` atom counts.
- Human-facing amounts in KVNC; wire/ledger amounts in atoms.

## 3. Emission curve

Smooth geometric decay:

- Genesis subsidy **s₀ = 10 KVNC/block**.
- Era length **E = 2,000,000 blocks**.
- Per-era decay **α = 3/4**: `s(era) = s(era−1) × 3/4` (integer floor).
- `subsidy_at(height) = s(height / E)`; eras ≥ 256 return 0.

Closed-form total emission:

```
total_emission = s₀ · E / (1 − α) = 10 × 2,000,000 × 4 = 80,000,000 KVNC
```

### Era table (selected)

| Era | Subsidy (KVNC) | Era emission (M KVNC) | Cumulative (M KVNC) |
|-----|----------------|-----------------------|---------------------|
| 0   | 10.000         | 20.00                 | 20.00               |
| 1   | 7.500          | 15.00                 | 35.00               |
| 2   | 5.625          | 11.25                 | 46.25               |
| 3   | 4.219          | 8.44                  | 54.69               |
| 4   | 3.164          | 6.33                  | 61.02               |
| 5   | 2.373          | 4.75                  | 65.76               |
| …   | → 0            | → 0                   | → 80.00             |

At ~1 block/s the first era lasts ≈ 23 days; the tail extends for decades.

## 4. Terminal supply & hard cap

- `MAX_SUPPLY = 90.2M KVNC = 90_200_000_000_000_000 atoms`.
- Enforced by per-block cumulative `native_minted` counter.
- A coinbase that would push `native_minted + claimed > MAX_SUPPLY` is rejected (`LedgerError::SupplyCapExceeded`).
- Genesis records premine + treasury as the initial `native_minted`.
- Counter serialized in checkpoint v7.

## 5. Distribution

| Component        | Amount    | Mechanism                                        |
|------------------|-----------|--------------------------------------------------|
| Founder premine  | 0.2M KVNC | Genesis coinbase output (existing 200 KVNC)      |
| Treasury         | 10M KVNC  | 10 × 1M RFC-005 vault tranches at genesis        |
| Curve emission   | 80M KVNC  | Block subsidies over the emission schedule       |
| **Total**        | **90.2M KVNC** | **< 100M**                                  |

### Treasury vesting

10 vault tranches of 1M KVNC each (RFC-005 time-lock vault composition):

- Tranche *k* (k = 1..=10): `VaultScript` with `absolute_time = k × 31,536,000` (≈ k years at 1 block/s).
- Beneficiary (CLAIM after expiry) = treasury.
- Owner (RECOVER before expiry) = treasury governance.
- Keys are currently placeholders pending a real key ceremony before mainnet.

## 6. Block subsidy & coinbase maturity

- Coinbase may claim up to `subsidy_at(height)` + fee share.
- **Coinbase maturity: `COINBASE_MATURITY = 100` blocks.**
- Spendable only at `height >= created_at + 100`; earlier spends rejected (`LedgerError::CoinbaseImmature`).
- Applies to all coinbase outputs (premine, treasury, subsidies).
- Transaction builder skips immature coinbases.

## 7. Fees

- **Fee floor:** `max(1, subsidy / 500_000)` atoms per byte.
- **Fee burn (75/25):** 75% of every transaction fee is burned; 25% goes to the block producer.
- Implementation: coinbase allowance = `subsidy + total_fees / 4` (integer division). Excess is unclaimable → destroyed. No special burn opcode or wire-format change.

## 8. Staking incentives & security budget

- Security budget per block = **subsidy + 25% of fees**.
- Hybrid admission (Stage 3): PoW blocks require real hash work; VRF-staked blocks require stake-weighted sortition.
- GHOSTDAG blue work (real PoW) remains the chain-selection work source.
- Bonded validators earn the same block reward as PoW miners when they win a slot.
- 10M treasury provides long-term development budget independent of declining subsidy.

## 9. Supply accounting

| Metric       | Definition                                                        |
|--------------|-------------------------------------------------------------------|
| `total`      | `native_minted` — cumulative minted (curve + premine + treasury)  |
| `circulating`| `total` − immature coinbases − unvested treasury tranches         |
| `burned`     | cumulative 75% fee burn                                           |

- `/api/head` will report subsidy, issuance, supply, and related fields.
- Prometheus: `kovanica_supply_total`, `kovanica_supply_circulating`, `kovanica_supply_minted`, `kovanica_supply_burned`.

## 10. Activation & migration

- Consensus fork. Testnet **resets** at activation.
- Checkpoint v6 → v7: per-output coinbase flag + `native_minted` counter.
- No transaction wire-format bump; sighash domain untouched.

## 11. Open questions & non-goals

- Treasury key ceremony required before mainnet.
- Mainnet profile parameters filled but dormant until RFC review/approval.
- Fee floor constant may be tuned from soak data.
- Non-goals: no rebasing, no demurrage, no algorithmic price stabilization, no governance token. KVNC is a pure ledger asset with a fixed, published issuance schedule.

------------------------------------------------------------

# RFC-006 Activation & Testnet-Reset Playbook

> Status: Steps 1–4 landed on branch `tokenomics/rfc-006-emission-curve`.  
> Steps 5–6 (treasury genesis + mainnet profile) and Step 7 (supply accounting) pending.  
> Activation is a **consensus fork** → the public testnet **resets**.

## What Changes at Activation

| Area                    | Pre-RFC-006                          | Post-RFC-006                                      |
|-------------------------|--------------------------------------|---------------------------------------------------|
| Emission                | Older schedule / higher subsidy      | Smooth geometric: s₀=10 KVNC, E=2M, α=3/4         |
| Hard cap                | None / soft                          | `MAX_SUPPLY = 90.2M KVNC` enforced via `native_minted` |
| Coinbase maturity       | None or different                    | Exactly 100 blocks (`COINBASE_MATURITY`)          |
| Fee model               | Flat or older floor                  | Floor = `max(1, subsidy/500_000)` atoms/byte; 75% burned / 25% to producer |
| Checkpoint format       | v6                                   | v7 (+ coinbase flag per output, `native_minted` counter) |
| Genesis                 | Current genesis                      | New genesis with premine 0.2M + 10×1M treasury vaults |
| All prior balances      | Valid                                | **Wiped** (testnet reset)                         |

## Detection: Pre vs Post Network

Always call `GET /api/head` and inspect:

```text
Post-RFC-006 indicators (expected once activated):
- presence of fields: subsidy, native_minted / total, circulating, burned
- min_fee that tracks the current subsidy (not a static 40000)
- genesis hash different from the pre-RFC-006 value
  (old: 3beecbebb6103ee24d1617fd87e920c949d613febbbcf6ca1453f3a4bf74056e)
```

Until the new fields appear, treat the network as pre-RFC-006 and do **not** hard-code the new economic constants into production clients.

## Client / Wallet Impact Checklist

After activation every client **must**:

1. Re-fetch `/api/head` and stop using any cached min_fee / subsidy.
2. Skip immature coinbases (created_at + 100 > current height) when selecting inputs.
3. Respect the dynamic fee floor (`max(1, subsidy / 500_000)` atoms per byte).
4. Expect `/api/prepare` to return fees calculated under the new rules.
5. Handle new ledger errors:
   - `LedgerError::SupplyCapExceeded`
   - `LedgerError::CoinbaseImmature`
6. Display supply metrics (`total`, `circulating`, `burned`) when the API exposes them.
7. Treat all pre-reset addresses/balances as gone — no migration path for testnet funds.

## Node Operator Checklist

- Wipe or move aside the old `KOVANICA_DATA` directory (new genesis will be written).
- Rebuild from the branch that contains the merged RFC-006 changes.
- Confirm checkpoint version is v7 after first start.
- Keep `KOVANICA_ALLOW_RESET=0` and `KOVANICA_FAUCET=0` on public nodes.
- Seed nodes: set `KOVANICA_PEERS=off` and use DNS-only names for clones.
- After restart, verify:
  ```sh
  curl -s http://127.0.0.1:8080/api/head
  # genesis, subsidy, native_minted / total should match the new RFC-006 values
  ```

## Tooling & Script Guidance

- Any hard-coded constants (old subsidy, old min_fee, old genesis) become bugs at activation.
- Prefer live `/api/head` values over compile-time constants.
- Emission math helpers (see `references/emission-math.md`) should be used by explorers and wallets that need to show “next era subsidy” or “remaining issuance”.
- The `scripts/check-head.sh` helper remains useful — after reset it will show the new genesis.

## Remaining Implementation Steps (from RFC)

| Step | Description                          | Status   |
|------|--------------------------------------|----------|
| 1–4  | Emission curve, MAX_SUPPLY, maturity, fee burn | Landed & green (785 tests) |
| 5    | Treasury genesis (10×1M vaults)      | Pending  |
| 6    | Mainnet profile                      | Pending  |
| 7    | Supply accounting / observability    | Pending  |

Do not declare the economic model “live on public testnet” until steps 5–7 are also merged and the reset has occurred.

## Safety Notes for Conversations

- Always warn that activation wipes the current testnet.
- Never assume old balances or old fee numbers survive.
- When generating client code, include explicit handling for the two new ledger errors and for immature coinbases.
- Point users to this file whenever they ask about “when the new tokenomics go live” or “what breaks at activation”.

------------------------------------------------------------

# Emission Math (RFC-006)

All amounts below are in **atoms** unless noted.  
`ATOM = 100_000_000` (1 KVNC).

## Constants

```rust
pub const ATOM: u64 = 100_000_000;
pub const S0_KVNC: u64 = 10;                    // genesis subsidy in KVNC
pub const S0: u64 = S0_KVNC * ATOM;             // 1_000_000_000 atoms
pub const ERA_LENGTH: u64 = 2_000_000;
pub const MAX_SUPPLY: u64 = 90_200_000 * ATOM;  // 90.2M KVNC
pub const COINBASE_MATURITY: u64 = 100;
```

Decay α = 3/4 per era (integer floor).

## subsidy_at(height)

```rust
/// Returns the block subsidy in atoms for the given height.
/// Eras ≥ 256 are clamped to 0.
pub fn subsidy_at(height: u64) -> u64 {
    let era = height / ERA_LENGTH;
    if era >= 256 {
        return 0;
    }
    let mut s = S0;
    for _ in 0..era {
        s = s * 3 / 4; // integer floor
        if s == 0 {
            break;
        }
    }
    s
}
```

Equivalent closed-form for total curve emission (ignoring the hard cap and parallel-block over-mint risk):

```
total_curve = S0 * ERA_LENGTH / (1 - α) = 10 * 2_000_000 * 4 = 80_000_000 KVNC
```

## Era table (KVNC, selected)

| Era | Subsidy/block | Era emission | Cumulative |
|-----|---------------|--------------|------------|
| 0   | 10.000        | 20.00 M      | 20.00 M    |
| 1   | 7.500         | 15.00 M      | 35.00 M    |
| 2   | 5.625         | 11.25 M      | 46.25 M    |
| 3   | 4.219         |  8.44 M      | 54.69 M    |
| 4   | 3.164         |  6.33 M      | 61.02 M    |
| 5   | 2.373         |  4.75 M      | 65.76 M    |
| …   | → 0           | → 0          | → 80.00 M  |

## Hard-cap enforcement (`native_minted`)

In a DAG, two blocks in each other’s anticone can each claim a full subsidy.  
The protocol therefore tracks a cumulative counter:

- Every block’s view state carries `native_minted` = selected-parent’s `native_minted` + this block’s coinbase claim.
- A coinbase that would make `native_minted + claimed > MAX_SUPPLY` is rejected with `LedgerError::SupplyCapExceeded`.
- Genesis initialises `native_minted` to premine (0.2M) + treasury (10M) = 10.2M KVNC.

Wallets and explorers that display “remaining supply” should use:

```text
remaining = MAX_SUPPLY - native_minted   (from /api/head once Step 7 lands)
```

## Fee floor & burn (for client fee estimation)

```rust
/// Minimum fee rate in atoms per byte of transaction.
pub fn fee_floor_atoms_per_byte(height: u64) -> u64 {
    let sub = subsidy_at(height);
    std::cmp::max(1, sub / 500_000)
}

/// Producer may claim at most subsidy + total_fees / 4.
/// The other 75 % is unclaimable → burned.
```

## Coinbase maturity check

```rust
pub fn is_coinbase_mature(created_at: u64, current_height: u64) -> bool {
    current_height >= created_at.saturating_add(COINBASE_MATURITY)
}
```

The node’s `prepare_transfer` (and friends) already skips immature coinbases; client-side selection should do the same to avoid `LedgerError::CoinbaseImmature`.

## Minimal Rust helper (copy-paste ready)

See `scripts/emission.rs` for a self-contained binary that prints subsidy, fee floor and remaining issuance for any height. Use it from explorers, wallets or CI checks.

------------------------------------------------------------

# Kovanica HTTP API Reference

All endpoints are available on both the public explorer (`https://explorer.kovanica.online`) and a local node (`http://127.0.0.1:8080` when run in explorer mode). The wallet app proxies the public explorer (CORS is closed on the node itself).

## Live Chain Parameters (always verify with /api/head)

### Pre-RFC-006 shape (current public testnet)

```json
{
  "network": "kovanica-testnet",
  "genesis": "3beecbebb6103ee24d1617fd87e920c949d613febbbcf6ca1453f3a4bf74056e",
  "tip": "<current tip hash>",
  "blocks": 6577,
  "min_fee": 40000,
  "atom": 100000000
}
```

### Post-RFC-006 shape (expected after activation + Step 7)

```json
{
  "network": "kovanica-testnet",
  "genesis": "<new genesis after reset>",
  "tip": "<current tip hash>",
  "blocks": <height>,
  "atom": 100000000,
  "min_fee": <dynamic, tracks subsidy>,
  "subsidy": <subsidy_at(height) in atoms>,
  "native_minted": <cumulative minted atoms>,
  "total": <same as native_minted or alias>,
  "circulating": <total − immature − unvested treasury>,
  "burned": <cumulative 75 % fee burn>
}
```

Detection rule: if `subsidy` / `native_minted` / `burned` fields are present → treat as post-RFC-006 network.

- 1 KVNC = 100_000_000 atoms
- GHOSTDAG k = 3
- After activation the fee floor becomes `max(1, subsidy / 500_000)` atoms per byte.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/head | Network, genesis, tip, height, atom, min_fee + (post-RFC-006) subsidy / supply fields |
| GET | /api/bootstrap | Listen address, peers, upstream probe |
| GET | /api/p2p | TCP listen + bootstrap peers |
| GET | /api/blocks | Octet-stream full block dump (used for clone catch-up) |
| GET | /api/state | Full DAG + flags |
| GET | /api/utxos?address=<addr> | Spendable UTXOs for address (immature coinbases excluded by node) |
| GET | /api/history?address=<addr> | Address deltas / history |
| GET | /api/origins | ISO3 origin pulses |
| GET | /api/spec | Plain-text technical spec |
| POST | /api/prepare | Build unsigned tx → returns sighash + fee + change |
| POST | /api/submit | Broadcast fully signed transaction |
| POST | /api/produce | Pack mempool into a block template |
| POST | /api/mine | Mine a coinbase block (only when enabled) |
| POST | /api/faucet | Testnet faucet (disabled on public explorer) |
| POST | /api/origin | Record a country origin pulse |

## Transaction Flow (client-side signing)

1. **Prepare**  
   `POST /api/prepare` with inputs/outputs.  
   Response contains:
   - sighash bytes (or hex)
   - calculated fee (respects current fee floor)
   - change output (if any)  
   The node already skips immature coinbases when selecting inputs.

2. **Sign offline**  
   Sign the raw sighash with Ed25519.  
   Result must be a 64-byte signature → 128 hex characters.  
   Nodes only accept 64-byte Ed25519 signatures.

3. **Submit**  
   `POST /api/submit` with the completed signed transaction.  
   The node never receives the private key or seed phrase.

## Post-RFC-006 Error Conditions Clients Must Handle

| Error | Meaning | Client action |
|-------|---------|---------------|
| `LedgerError::SupplyCapExceeded` | Coinbase would push `native_minted` over `MAX_SUPPLY` | Do not retry the same coinbase claim; surface “supply cap reached” |
| `LedgerError::CoinbaseImmature` | Attempt to spend a coinbase younger than 100 blocks | Wait until `height >= created_at + 100`; refresh UTXO set |

`/api/prepare` should never return immature coinbases, but defensive clients still check maturity before building transactions offline.

## Fee Rules After Activation

- Floor = `max(1, subsidy_at(height) / 500_000)` atoms per byte.
- 75 % of every fee is burned (unclaimable by the producer).
- Producer may claim at most `subsidy + total_fees / 4`.
- Clients should estimate fees using the live `subsidy` (or `min_fee`) from `/api/head` rather than any hard-coded constant.

## Important Security Notes

- All signing happens in the browser / client (wallet, CLI, or custom tool).
- Never send seed phrases or private keys to any `/api/*` endpoint.
- Public explorer keeps reset and open faucet disabled.
- Prefer DNS-only seed names (`seed.kovanica.online`) for P2P; Cloudflare orange-cloud names do not forward TCP 9000.
- After the RFC-006 testnet reset, all prior balances are gone — treat addresses as new.

------------------------------------------------------------

# GHOSTDAG Notes for Kovanica (k=3)

## Core parameters

- `k = 3` (fixed for current testnet / RFC-006 era)
- Chain selection work source = **blue work** (real PoW)
- Hybrid admission (Stage 3 vision): PoW blocks + VRF-staked blocks
- Staked blocks pin nominal work so cheaply-inflatable blue weight cannot dominate selection

## Practical implications of k=3

| Topic | Implication |
|-------|-------------|
| Finality depth | Expect deeper confirmation targets than Bitcoin’s 6; practical wallets often wait for blue-score advance of several k-windows |
| Reorg risk | Parallel blocks in the anticone are normal; a block is only “final” once it is well inside the selected chain and its anticone is stable |
| Blue vs red | Blue blocks contribute to selected-chain work; red blocks are still stored but do not extend the selected tip’s work |
| Parallel minting | Two blocks in each other’s anticone can each claim a full subsidy → this is exactly why `native_minted` + `MAX_SUPPLY` hard-cap exists |

## Interaction with RFC-006 tokenomics

- Every block’s view carries `native_minted` inherited from its **selected parent** + its own coinbase claim.
- Because GHOSTDAG can accept parallel blocks, the cumulative counter (not the simple curve sum) is the real supply ceiling.
- A coinbase that would exceed `MAX_SUPPLY` is rejected even if the pure geometric curve still has room.

## Testing & analysis tips

1. When writing consensus tests, always construct both a selected-parent chain and an anticone of width ≤ k.
2. Verify that `native_minted` on a block equals selected-parent’s value + this block’s claim (or is rejected).
3. For wallet UX, prefer “blue-score confirmations” or “depth in selected chain” over raw block height when showing finality.
4. Explorers should visualise the GHOSTDAG graph (selected chain highlighted, anticone visible) — the public explorer already does this.

## Security-budget note

Security budget per block = subsidy + 25 % of fees.  
As subsidy decays, fee revenue and (later) VRF stake become more important. GHOSTDAG blue-work remains the ultimate chain-selection signal; stake only gates admission of staked blocks.

------------------------------------------------------------

# Operator vs Participant Matrix

Clear guidance on which `KOVANICA_*` flags are appropriate for each role.

| Variable / Role            | Home participant | Public explorer / API | Seed node | Mining / producer node |
|----------------------------|------------------|-----------------------|-----------|------------------------|
| `KOVANICA_POW`             | 1                | 1                     | 1         | 1                      |
| `KOVANICA_MINE`            | 0                | 0                     | 0         | 1 (if intentional)     |
| `KOVANICA_MINE_SECS`       | 120              | 120                   | 120       | ≥ 120                  |
| `KOVANICA_FAUCET`          | 0                | 0                     | 0         | 0                      |
| `KOVANICA_ALLOW_RESET`     | 0                | 0                     | 0         | 0                      |
| `KOVANICA_OPERATOR`        | 0                | 0 or 1 (UI only)      | 0         | 0                      |
| `KOVANICA_LISTEN`          | 0.0.0.0:9000 (optional) | 0.0.0.0:9000     | 0.0.0.0:9000 | 0.0.0.0:9000        |
| `KOVANICA_PEERS`           | seed.kovanica.online:9000 | seed…            | **off**   | seed…                  |
| `KOVANICA_DATA`            | persistent       | persistent            | persistent| persistent             |

## Rules of thumb

- **Never** enable `ALLOW_RESET` or open `FAUCET` on any node that is reachable from the public internet.
- Seed nodes must not dial themselves (`KOVANICA_PEERS=off` or empty).
- Home users only need outbound 9000; inbound is optional.
- After RFC-006 activation the same matrix still applies — the economic changes do not relax operator safety flags.
- Document the exact flag set in every run script or systemd unit you produce.

------------------------------------------------------------

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

------------------------------------------------------------

# Kovanica Project Planning Playbook

Act as a project-plan mastermind when the user asks for roadmaps, feature breakdowns, or delivery plans around Kovanica.

## Layered Decomposition

Always split work into three layers:

1. **Consensus-safe**  
   Changes that affect GHOSTDAG ordering, block validation, or k-parameter behavior.  
   Highest risk, longest review, requires extensive testnet soak.

2. **Ledger-safe**  
   UTXO set, fee calculation, coinbase rules, min-fee enforcement, sighash construction.  
   Medium risk; must preserve existing transaction validity.

3. **Client-only**  
   Wallet UI, explorer visualizations, origin map, hardware wallet integration, CLI ergonomics, documentation.  
   Lowest consensus risk; can ship independently.

## Recommended Sequencing (Testnet → Mainnet)

### Phase 0 — Stability
- Reliable P2P catch-up on TCP 9000
- Deterministic `/api/head` and `/api/blocks` dumps
- Clear operator vs participant environment variable defaults
- Documentation of current min_fee, subsidy schedule, genesis

### Phase 0.5 — RFC-006 Tokenomics Activation (critical path)
- Land remaining steps (treasury genesis, mainnet profile, supply accounting)
- Testnet **reset** at activation (consensus fork)
- Verify MAX_SUPPLY enforcement, 100-block maturity, 75/25 fee burn
- Update all client tooling and `/api/head` consumers to new numbers
- Treasury key ceremony planning (placeholders → real keys before mainnet)

### Phase 1 — API & Tooling
- Stable `/api/prepare` + `/api/submit` contract under new fee floor + burn rules
- Reference Ed25519 client (Rust + JS/TS)
- CLI wallet parity with web wallet
- Multisig (RFC-001) end-to-end flow documented and tested
- Supply metrics exposure (`total` / `circulating` / `burned`)

### Phase 2 — Wallet & UX
- Hardware wallet support (accounts 0–2 already sketched)
- Improved GHOSTDAG graph visualization
- Mobile APK / IPA release pipeline hardening
- Origin map and network status polish
- Clear display of immature coinbases and vested treasury status

### Phase 3 — Advanced Features
- More sophisticated multisig / threshold schemes
- Fee market observability and Prometheus supply series
- Light-client / SPV-style proofs if desired
- Mainnet readiness checklist (economic parameters locked, security audit, governance, real treasury keys)

## Risk Register (always surface these)

- P2P connectivity through Cloudflare / DNS-only requirement
- GHOSTDAG k=3 effects on finality and reorg depth
- Min-fee / fee-floor changes breaking wallets after RFC-006
- Supply-cap rejection of oversize coinbases
- Coinbase maturity (100 blocks) surprises for miners/wallets
- Seed / private-key leakage into logs or node process
- Operator flags (`ALLOW_RESET`, open faucet) left enabled on public nodes
- Data directory loss = local chain view loss
- Treasury placeholder keys not replaced before mainnet
- Testnet reset at RFC-006 activation — all prior balances wiped

## Delivery Artifacts

When producing plans, prefer:
- Clear milestone table (Phase / Goal / Exit criteria / Risks)
- Concrete environment variable matrices
- “Definition of done” that includes matching public `/api/head` after sync
- Explicit “do not ship” items (e.g. reset enabled, faucet open on seed)

## Communication Style

- Be precise about current testnet numbers (pull live `/api/head` when possible)
- Prefer actionable checklists over vague “improve security”
- Call out when a request belongs in consensus vs client layer
- Offer both minimal viable path and robust production path

------------------------------------------------------------

# Rust Client Notes for Kovanica

## Core dependencies

```toml
[dependencies]
ed25519-dalek = "2"
reqwest = { version = "0.12", features = ["json", "blocking"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
hex = "0.4"
# tokio = { version = "1", features = ["full"] }  # if you prefer async
```

## Signing pattern (mandatory)

1. Obtain sighash from `POST /api/prepare` (raw bytes or hex).
2. Sign with `ed25519_dalek::SigningKey`.
3. Encode the 64-byte signature as **128 lowercase hex** characters.
4. Include that hex in the body of `POST /api/submit`.

```rust
use ed25519_dalek::{SigningKey, Signer};
use hex;

// sighash: &[u8] from prepare response
let signature = signing_key.sign(sighash);
let sig_hex = hex::encode(signature.to_bytes()); // exactly 128 chars
```

## Key safety rules

- Never put the seed or `SigningKey` into any request body or log.
- Prefer deriving keys from the same path the official wallet uses (confirm against current wallet source).
- Keep signing fully client-side; the node only verifies 64-byte Ed25519 signatures.

## Minimal typed client skeleton

A robust client should:

1. Call `GET /api/head` on startup and cache `atom`, `min_fee` / `subsidy`, and (post-RFC-006) supply fields.
2. Expose a high-level `transfer(from, to, amount)` that internally does prepare → sign → submit and **never** accepts a private key in its public API surface (pass a signer trait/callback instead).
3. Filter UTXOs client-side for coinbase maturity (`created_at + 100 ≤ current_height`) even though the node already skips them.
4. Surface the two new ledger errors:
   - `SupplyCapExceeded`
   - `CoinbaseImmature`
5. After the RFC-006 reset, treat any previously cached addresses/balances as invalid.

## Fee estimation after activation

```rust
fn fee_floor_atoms_per_byte(subsidy: u64) -> u64 {
    std::cmp::max(1, subsidy / 500_000)
}
```

Prefer the live `subsidy` (or `min_fee`) from `/api/head` over any compile-time constant.

## Emission helper

For explorers or wallets that need “next-era subsidy” or remaining issuance, reuse the pure functions in `scripts/emission.rs` / `references/emission-math.md`.

## Checklist when generating client code

- [ ] Live `/api/head` used for fee / subsidy
- [ ] Immature coinbases skipped
- [ ] 75/25 burn model understood (client only estimates; node enforces)
- [ ] New ledger errors handled
- [ ] No private keys in logs or HTTP bodies
- [ ] Works against both pre- and post-RFC-006 `/api/head` shapes (feature-detect the new fields)


------------------------------------------------------------

# Mainnet Readiness Checklist

Use this before any mainnet parameter freeze or launch announcement.

## Consensus & economics (must be locked)

- [ ] RFC-006 fully merged (steps 5–7 included: treasury genesis, mainnet profile, supply accounting)
- [ ] Testnet reset completed and soaked for ≥ 2 weeks with no supply-cap or maturity bugs
- [ ] `MAX_SUPPLY`, era length, α, coinbase maturity, fee floor constant reviewed and frozen
- [ ] Treasury key ceremony completed; placeholder keys removed
- [ ] Checkpoint v7 (or later) is the only format on the network
- [ ] GHOSTDAG `k` value confirmed for mainnet (currently 3 on testnet)

## Networking & ops

- [ ] Multiple independent seed nodes (DNS-only / grey-cloud) with documented IPs
- [ ] P2P on TCP 9000 proven under partition and high-latency conditions
- [ ] No reliance on Cloudflare-proxied hostnames for P2P
- [ ] Operator flags (`ALLOW_RESET`, open faucet) impossible to enable on public binaries or clearly gated
- [ ] Monitoring: Prometheus series for supply, tip, peer count, orphan rate

## Clients & ecosystem

- [ ] Official wallet + CLI handle post-RFC-006 `/api/head` fields and new ledger errors
- [ ] Immature coinbase filtering verified in all official clients
- [ ] Multisig (KVP-101), multi-asset (KVP-102), vaults (KVP-105) smoke-tested on the reset testnet
- [ ] Mobile APK/IPA and light-node/FFI paths tested against mainnet genesis parameters
- [ ] Documentation (site, `/docs`, roadmap) updated to mainnet numbers

## Security & process

- [ ] External review or audit of consensus-critical paths (emission, cap, maturity, script machine)
- [ ] Responsible-disclosure contact published
- [ ] Genesis block hash and parameters published in multiple independent places before launch
- [ ] Clear statement that testnet balances do not carry over

## Go / no-go

Do **not** announce mainnet until every box above is checked and the final genesis is reproducible by at least two independent parties.

------------------------------------------------------------

# FAQ & Common Pitfalls

## Networking

**Q: My node won’t sync.**  
A: Use `seed.kovanica.online:9000` (DNS-only / grey-cloud). Never point `KOVANICA_PEERS` at `explorer.kovanica.online:9000` — Cloudflare does not forward TCP 9000.

**Q: Do I need inbound 9000 open?**  
A: Only if you want to serve other peers. Outbound to the seed is enough to catch up.

## Economics (RFC-006)

**Q: Why is there a hard cap if the curve already sums to 80 M?**  
A: In a DAG, parallel blocks in each other’s anticone can each mint a full subsidy. `native_minted` + `MAX_SUPPLY` (90.2 M) is the real ceiling.

**Q: When can I spend a coinbase?**  
A: Only after 100 blocks (`COINBASE_MATURITY`). The node’s `prepare` already skips immature outputs; clients should too.

**Q: Who gets the fees?**  
A: 25 % to the block producer, 75 % burned (unclaimable). There is no burn opcode — the coinbase allowance is simply capped.

**Q: Will my testnet coins survive the RFC-006 activation?**  
A: No. Activation is a consensus fork that resets the testnet.

## Keys & signing

**Q: Does the node ever see my seed?**  
A: No. Signing is client-side (browser, CLI, or your own tool). Only the 64-byte Ed25519 signature (128 hex) is submitted.

**Q: What is the sighash?**  
A: The bytes returned by `POST /api/prepare`. Sign those exact bytes; do not re-serialize the transaction yourself unless you match the node’s encoding 1:1.

## Multi-asset & scripts

**Q: Is KVP-102 an ERC-20?**  
A: No. It is a native multi-asset UTXO model with per-asset conservation.

**Q: Can I use arbitrary Bitcoin Script?**  
A: No. Script v2 (RFC-003) is a bounded machine (CLTV/CSV/hash-lock, etc.). Keep scripts inside that model.

## Operator flags

**Q: Can I turn on the faucet or reset on a public node?**  
A: You can, but you must not. Keep `KOVANICA_FAUCET=0` and `KOVANICA_ALLOW_RESET=0` on anything reachable from the internet.

------------------------------------------------------------

# Kovanica Cheat Sheet

## One-liners

```bash
# Install node
curl -sSfL https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.sh | bash

# Participant node
export KOVANICA_POW=1 KOVANICA_MINE=0 KOVANICA_FAUCET=0 KOVANICA_ALLOW_RESET=0
export KOVANICA_OPERATOR=0 KOVANICA_LISTEN=0.0.0.0:9000
export KOVANICA_PEERS=seed.kovanica.online:9000 KOVANICA_DATA=$PWD/data
./target/release/kovanica-node explorer 127.0.0.1:8080

# Check sync
curl -s http://127.0.0.1:8080/api/head
curl -s https://explorer.kovanica.online/api/head
```

## Constants (RFC-006)

| Name | Value |
|------|--------|
| ATOM | 100_000_000 |
| S0 | 10 KVNC / block |
| ERA_LENGTH | 2_000_000 blocks |
| α | 3/4 per era |
| MAX_SUPPLY | 90.2 M KVNC |
| Premine | 0.2 M |
| Treasury | 10 M (10×1 M vaults) |
| Curve emission | 80 M |
| COINBASE_MATURITY | 100 blocks |
| Fee split | 75 % burn / 25 % producer |
| Fee floor | max(1, subsidy/500_000) atoms/byte |
| k (GHOSTDAG) | 3 |
| P2P | TCP :9000 only |

## Transaction flow

1. `POST /api/prepare` → sighash + fee + change  
2. Sign sighash with Ed25519 → 128 hex  
3. `POST /api/submit`

## Key URLs

- Site: https://kovanica.online  
- Explorer: https://explorer.kovanica.online  
- Wallet: https://wallet.kovanica.online  
- Roadmap: https://kovanica.online/roadmap  
- Node: https://github.com/KovanicaDAG/kovanica-node  
- Seed: `seed.kovanica.online:9000` (grey-cloud)

------------------------------------------------------------

# Scripts

## scripts/check-head.sh

```bash
#!/usr/bin/env bash
# Quick health / sync check against local node and public explorer.
# Usage: ./check-head.sh [local_base_url]
# Default local: http://127.0.0.1:8080

set -euo pipefail

LOCAL="${1:-http://127.0.0.1:8080}"
PUBLIC="https://explorer.kovanica.online"

echo "=== Local head ($LOCAL) ==="
curl -sS "$LOCAL/api/head" | jq . || curl -sS "$LOCAL/api/head"
echo
echo "=== Public head ($PUBLIC) ==="
curl -sS "$PUBLIC/api/head" | jq . || curl -sS "$PUBLIC/api/head"
echo
echo "Compare genesis and tip. They should match after full sync."```

## scripts/emission.rs

```rust
// Minimal RFC-006 emission helper.
// Build: rustc -O emission.rs -o emission
// Usage: ./emission [height]

const ATOM: u64 = 100_000_000;
const S0: u64 = 10 * ATOM; // 10 KVNC
const ERA_LENGTH: u64 = 2_000_000;
const MAX_SUPPLY: u64 = 90_200_000 * ATOM;

fn subsidy_at(height: u64) -> u64 {
    let era = height / ERA_LENGTH;
    if era >= 256 {
        return 0;
    }
    let mut s = S0;
    for _ in 0..era {
        s = s * 3 / 4;
        if s == 0 {
            break;
        }
    }
    s
}

fn fee_floor_atoms_per_byte(height: u64) -> u64 {
    let sub = subsidy_at(height);
    std::cmp::max(1, sub / 500_000)
}

fn kvnc(atoms: u64) -> f64 {
    atoms as f64 / ATOM as f64
}

fn main() {
    let height: u64 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);

    let sub = subsidy_at(height);
    let floor = fee_floor_atoms_per_byte(height);
    let era = height / ERA_LENGTH;

    println!("height          : {}", height);
    println!("era             : {}", era);
    println!("subsidy         : {} atoms ({:.8} KVNC)", sub, kvnc(sub));
    println!("fee floor       : {} atoms/byte", floor);
    println!("MAX_SUPPLY      : {} atoms ({:.1} M KVNC)", MAX_SUPPLY, kvnc(MAX_SUPPLY) / 1_000_000.0);
    println!("(remaining supply requires live native_minted from /api/head)");
}```

---

*End of Kovanica Blockchain Developer skill pack.*
