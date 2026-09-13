---
source: skills/rfc-005-vault/SKILL.md
name: rfc-005-vault
synced_at: 2026-09-12T08:33:08.795839+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-005-vault — synced from skills/rfc-005-vault/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.795839+00:00

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

The same `VaultScript` primitive is available for ordinary users (escrow, time-locked savings, etc.). Wallets should expose a simple "lock until height / date" UI that constructs the identical script type.

## Safety

- Placeholder treasury keys must never be used on mainnet.
- Any tool that generates vaults must make the absolute_time and the two keys explicit in the UI and in any exported descriptor.
- After the RFC-006 testnet reset the treasury vaults will be re-created at the new genesis; old vault addresses disappear with the rest of the chain.
