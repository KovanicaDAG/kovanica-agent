---
source: skills/rfc-003-stealth-script/SKILL.md
name: rfc-003-stealth-script
synced_at: 2026-09-12T08:33:08.795385+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-003-stealth-script — synced from skills/rfc-003-stealth-script/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.795385+00:00

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

1. Stealth sends require the recipient's public scan/view key.
2. Wallets that support stealth must implement the ECDH + view-tag scan path.
3. Any script that uses CLTV/CSV must be validated against the bounded machine; do not assume Bitcoin Script compatibility.
4. Hardware-wallet support for stealth is still evolving — confirm against current FFI.

## See also

- RFC-005 re-uses the CLTV/CSV primitives for vaults
- RFC-004 re-uses hash-lock for HTLCs
