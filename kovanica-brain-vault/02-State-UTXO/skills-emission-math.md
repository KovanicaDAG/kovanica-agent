---
source: skills/emission-math/SKILL.md
name: emission-math
synced_at: 2026-09-12T08:33:08.792844+00:00
synced_from: skills
tags: [skill, kovanica]
---
# emission-math — synced from skills/emission-math/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.792844+00:00

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

In a DAG, two blocks in each other's anticone can each claim a full subsidy.  
The protocol therefore tracks a cumulative counter:

- Every block's view state carries `native_minted` = selected-parent's `native_minted` + this block's coinbase claim.
- A coinbase that would make `native_minted + claimed > MAX_SUPPLY` is rejected with `LedgerError::SupplyCapExceeded`.
- Genesis initialises `native_minted` to premine (0.2M) + treasury (10M) = 10.2M KVNC.

Wallets and explorers that display "remaining supply" should use:

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

The node's `prepare_transfer` (and friends) already skips immature coinbases; client-side selection should do the same to avoid `LedgerError::CoinbaseImmature`.

## Minimal Rust helper (copy-paste ready)

See `scripts/SKILL.md` for a self-contained binary that prints subsidy, fee floor and remaining issuance for any height. Use it from explorers, wallets or CI checks.
