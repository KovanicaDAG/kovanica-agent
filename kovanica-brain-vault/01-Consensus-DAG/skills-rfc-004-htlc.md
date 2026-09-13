---
source: skills/rfc-004-htlc/SKILL.md
name: rfc-004-htlc
synced_at: 2026-09-12T08:33:08.795629+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-004-htlc — synced from skills/rfc-004-htlc/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.795629+00:00

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
3. Both parties should verify the on-chain HTLC script before considering the swap "locked".
4. After RFC-006 the normal fee-floor and maturity rules apply to the funding and claim transactions.

## Composition

HTLCs are built on the script-v2 machine from RFC-003 (hash-lock + CLTV/CSV).
