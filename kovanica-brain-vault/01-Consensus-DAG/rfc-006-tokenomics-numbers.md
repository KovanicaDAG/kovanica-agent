---
key: rfc-006-tokenomics-numbers
value: "MAX_SUPPLY=90.2M KVNC (90_200_000_000_000_000 atoms). S0=10 KVNC/block. ERA_LENGTH=2_000_000. Decay alpha=3/4. COINBASE_MATURITY=100. Fee split 75/25. Fee floor=max(1,subsidy/500_000). Premine=0.2M, Treasury=10M (10*1M vaults), Curve=80M. Total=90.2M."
role: dev
learned_at: 2026-09-12T00:00:00+00:00
source: RFC-006 spec + tokenomics.rs
tags: [rfcs, tokenomics, constants, code-sample]
---

# RFC-006 Tokenomics Numbers

**Canonical constants — 2026-09-12**

These are the numbers that MUST be used in any code, config, or client that targets the RFC-006 model.

## Constants (atoms unless noted)

```rust
pub const ATOM: u64 = 100_000_000;
pub const S0_KVNC: u64 = 10;                    // genesis subsidy in KVNC
pub const S0: u64 = S0_KVNC * ATOM;             // 1_000_000_000 atoms
pub const ERA_LENGTH: u64 = 2_000_000;
pub const MAX_SUPPLY: u64 = 90_200_000 * ATOM;  // 90.2M KVNC
pub const COINBASE_MATURITY: u64 = 100;
```

## Subsidy function

```rust
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

## Fee floor

```rust
pub fn fee_floor_atoms_per_byte(height: u64) -> u64 {
    let sub = subsidy_at(height);
    std::cmp::max(1, sub / 500_000)
}
```

## Coinbase maturity check

```rust
pub fn is_coinbase_mature(created_at: u64, current_height: u64) -> bool {
    current_height >= created_at.saturating_add(COINBASE_MATURITY)
}
```

## Distribution

| Component | Amount | Mechanism |
|-----------|--------|-----------|
| Founder premine | 0.2M KVNC | Genesis coinbase output |
| Treasury | 10M KVNC | 10 × 1M RFC-005 vault tranches |
| Curve emission | 80M KVNC | Block subsidies over schedule |
| **Total** | **90.2M KVNC** | **< 100M** |

## Treasury vesting schedule

10 tranches × 1M KVNC. Tranche k: `absolute_time = k × 31_536_000` (≈ k years at 1 blk/s).

| Tranche | absolute_time | ≈ years |
|---------|---------------|---------|
| 1 | 31_536_000 | 1 |
| 2 | 63_072_000 | 2 |
| … | … | … |
| 10 | 315_360_000 | 10 |

## Cross-reference

- `skills/rfc-006-tokenomics/SKILL.md` — full spec
- `skills/emission-math/SKILL.md` — math helpers
- `skills/rust-client-notes/SKILL.md` — client-side usage
- `scripts/emission.rs` — standalone helper binary
