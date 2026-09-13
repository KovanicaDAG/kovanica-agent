---
source: skills/rfc-001-multisig/SKILL.md
name: rfc-001-multisig
synced_at: 2026-09-12T08:33:08.794945+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-001-multisig — synced from skills/rfc-001-multisig/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.794945+00:00

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
