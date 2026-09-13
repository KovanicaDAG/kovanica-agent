---
source: skills/project-planning/SKILL.md
name: project-planning
synced_at: 2026-09-12T08:33:08.794706+00:00
synced_from: skills
tags: [skill, kovanica]
---
# project-planning — synced from skills/project-planning/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.794706+00:00

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
- "Definition of done" that includes matching public `/api/head` after sync
- Explicit "do not ship" items (e.g. reset enabled, faucet open on seed)

## Communication Style

- Be precise about current testnet numbers (pull live `/api/head` when possible)
- Prefer actionable checklists over vague "improve security"
- Call out when a request belongs in consensus vs client layer
- Offer both minimal viable path and robust production path
