---
source: skills/scripts/SKILL.md
name: scripts
synced_at: 2026-09-12T08:33:08.797173+00:00
synced_from: skills
tags: [skill, kovanica]
---
# scripts — synced from skills/scripts/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.797173+00:00

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
echo "Compare genesis and tip. They should match after full sync."
```

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
}
```
