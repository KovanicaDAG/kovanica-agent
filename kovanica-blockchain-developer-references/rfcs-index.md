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