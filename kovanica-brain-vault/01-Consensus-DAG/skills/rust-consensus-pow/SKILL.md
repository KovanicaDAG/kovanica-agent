---
name: rust-consensus-pow
description: Use when implementing Proof of Work consensus in Rust: block hashing with SHA-256d, nonce search, difficulty/target adjustment, validation of PoW, and the chain selection rule (heaviest chain / most cumulative work).
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [blockchain, PoW, proof-of-work, SHA-256d, nonce, difficulty, target, chain-selection, cumulative-work]
    related_skills: [blockchain-fundamentals, rust-crypto, rust-crypto-primitives, rust-block-propagation]
---

# Rust Proof of Work Consensus

## Overview

Proof of Work (PoW) is a consensus mechanism where the right to create a block is earned by expending computational work: finding a nonce such that the block's hash is below a target difficulty. The chain with the most cumulative work is canonical. PoW is used by Bitcoin (SHA-256d), Litecoin (Scrypt), and others.

This skill covers the practical implementation of PoW in Rust: block header hashing, the nonce search loop, difficulty adjustment, and validation. For DAG-based PoW (GHOSTDAG), see the GHOSTDAG skill.

## When to Use

- Implementing a PoW-based blockchain
- Mining logic (nonce search, block template construction)
- Validating that a block satisfies the PoW requirement
- Difficulty/target adjustment algorithms
- Chain selection by cumulative work

**Don't use for:** PoS consensus, DAG-based consensus (GHOSTDAG), or protocols that use a different PoW algorithm (e.g., Scrypt, Ethash) — the hashing details differ.

## Block Header and Hash

### Header Structure

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BlockHeader {
    version: u32,
    prev_block_hash: [u8; 32],
    merkle_root: [u8; 32],
    timestamp: u64,
    difficulty: u32,        // or target; depends on design
    nonce: u64,
}
```

The block hash is `hash(header)`. In Bitcoin, the header is hashed twice (SHA-256d):

```rust
// Bitcoin-style SHA-256d: SHA256(SHA256(header))
fn hash_header(header: &BlockHeader) -> [u8; 32] {
    use sha2::Sha256;
    let mut hasher = Sha256::new();
    // serialize header in a canonical format (usually little-endian for integers)
    hasher.update(&serialize_header_le(header));
    let first = hasher.finalize();
    let mut hasher2 = Sha256::new();
    hasher2.update(&first);
    hasher2.finalize().into()
}
```

**Canonical serialization matters.** The hash depends on exactly how the header is serialized. Define the serialization format precisely (byte order, field order, padding) and test it. For network compatibility, match the reference implementation.

### Target and Difficulty

The difficulty is a number; the target is the threshold the hash must be below.

```rust
// A block is valid if hash < target
// target = max_target / difficulty

fn is_valid_pow(header: &BlockHeader, difficulty: u32) -> bool {
    let hash = hash_header(header);
    let target = TARGET_MAX / difficulty;   // careful with integer division
    hash < target   // compare as big-endian integers
}
```

If difficulty is stored as a compact representation (like Bitcoin's "bits"), decode it to a target. The compact form is a 4-byte value where the first byte is the exponent and the rest is the significand.

```rust
// Bitcoin-style compact difficulty
fn compact_to_target(bits: u32) -> [u8; 32] {
    let exponent = (bits >> 24) as u32;
    let significand = bits & 0x00ffffff;
    // target = significand * 256^(exponent - 3)
    // ...
}
```

## Nonce Search (Mining)

### The Mining Loop

```rust
fn mine_block(header: &mut BlockHeader, difficulty: u32) -> bool {
    loop {
        let hash = hash_header(header);
        if hash < target_from_difficulty(difficulty) {
            return true;   // found a valid nonce
        }
        header.nonce += 1;
        // overflow handling: if nonce wraps, increment extra nonce or timestamp
        if header.nonce == 0 {
            // nonce overflowed — adjust extra nonce or timestamp
            // ...
        }
    }
}
```

**Optimization:** the hash is dominated by the nonce changing. To avoid re-hashing the entire header every iteration, some implementations hash the header without the nonce once, then only hash the nonce part. This is a performance optimization but must produce the same result as the full hash.

### Mining with Multiple Threads

```rust
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

fn mine_parallel(header: BlockHeader, difficulty: u32, num_threads: usize) -> Option<BlockHeader> {
    let nonce_start = AtomicU64::new(0);
    let mut handles = vec![];

    for i in 0..num_threads {
        let header = header.clone();
        let start = Arc::clone(&nonce_start);
        let difficulty = difficulty;
        let handle = std::thread::spawn(move || {
            let mut local_nonce = i * (u64::MAX / num_threads);
            loop {
                let mut h = header.clone();
                h.nonce = local_nonce;
                if is_valid_pow(&h, difficulty) {
                    return Some(h);
                }
                local_nonce += num_threads;
                if local_nonce == 0 { break; }   // overflow
            }
            None
        });
        handles.push(handle);
    }

    for handle in handles {
        if let Some(found) = handle.join().unwrap() {
            return Some(found);
        }
    }
    None
}
```

**Thread safety:** the nonce is a shared counter or each thread has a range. Avoid contention on a single atomic counter if possible — partition the nonce space.

### Extra Nonce and Timestamp

A 64-bit nonce may not be enough for high difficulties. Common approaches:
- **Extra nonce in the coinbase transaction** (Bitcoin) — changes the Merkle root, so the header hash changes even with the same nonce.
- **Timestamp adjustment** — within allowed bounds (not too far in the future, not too far in the past).

## Difficulty Adjustment

Difficulty must adjust to keep block time stable as hash power changes.

### Bitcoin-style: 2016-block adjustment

```rust
// Every 2016 blocks, adjust difficulty to target 10-minute blocks
fn adjust_difficulty(prev_blocks: &[Block], new_block: &Block) -> u32 {
    if prev_blocks.len() < 2016 {
        return new_block.difficulty;   // no adjustment yet
    }

    let last = &prev_blocks[0];
    let oldest = &prev_blocks[2015];

    let actual_time = new_block.timestamp - oldest.timestamp;
    let expected_time = 2016 * 10 * 60;   // 10 minutes in seconds

    let mut new_diff = (new_block.difficulty as u128 * actual_time as u128 / expected_time as u128) as u32;

    // Limit adjustment: max 4x increase, max 0.25x decrease
    new_diff = new_diff.max(new_block.difficulty / 4);
    new_diff = new_diff.min(new_block.difficulty * 4);

    new_diff
}
```

### Other adjustment algorithms

- **Ethereum (pre-merge):** used a formula based on block count and parent timestamp, with a gas limit adjustment.
- **KGW (Kimoto's Gravity Well):** per-block difficulty adjustment with lookback.
- **Dark Gravity Wave:** variants of KGW.

Choose an algorithm that matches your design goals (fast adjustment for variable hash power, smooth adjustment for stability).

## Chain Selection: Heaviest Chain

The canonical chain is the one with the most cumulative work (sum of difficulty/difficulty-adjusted hashes).

```rust
fn cumulative_work(chain: &[Block]) -> u128 {
    chain.iter().map(|b| work_from_difficulty(b.difficulty)).sum()
}

fn select_canonical(chains: &[Vec<Block>]) -> &[Block] {
    chains.iter().max_by_key(|chain| cumulative_work(chain)).unwrap()
}
```

**Important:** "most work" is not "most blocks." A chain with fewer blocks but higher difficulty can win. This is why a low-difficulty chain can't overtake a high-difficulty chain even with more blocks.

## Validation

A newly received block must pass:

```rust
fn validate_block(block: &Block, prev_block: Option<&Block>, difficulty: u32) -> Result<(), ValidationFailure> {
    // 1. Header structure valid
    // 2. Previous hash matches (if prev_block provided)
    // 3. Timestamp reasonable (not too far in future, not before prev block)
    // 4. PoW valid: hash(block_header) < target
    // 5. Merkle root matches transactions
    // 6. Transactions valid (signatures, no double-spend, fees, etc.)
    // 7. Coinbase transaction valid (if applicable)
    // 8. Difficulty matches the adjustment rule
    // ...
}
```

Validation must be deterministic and fast — every node validates every block. Don't skip validation for "trusted" blocks.

## Verification Checklist

- [ ] Can serialize a block header in the canonical format and hash it
- [ ] Can implement the nonce search loop with overflow handling
- [ ] Can parallelize the search across threads with partitioned nonces
- [ ] Can compute the target from difficulty and check hash < target
- [ ] Can implement a difficulty adjustment algorithm (e.g., 2016-block with bounds)
- [ ] Can compute cumulative work and select the heaviest chain
- [ ] Can validate a block's PoW and other header fields
- [ ] Understands the difference between difficulty (a number) and target (the threshold)

## Common Pitfalls

1. **Incorrect serialization of the header.** Byte order (endianness), field order, and padding must be exact. A one-byte difference gives a different hash. Test against known test vectors.

2. **Not handling nonce overflow.** A 64-bit nonce can wrap. Plan for what happens when the nonce space is exhausted (extra nonce, timestamp, or restart).

3. **Difficulty adjustment unbounded.** Without adjustment limits, difficulty can swing wildly if hash power changes suddenly. Cap the adjustment factor.

4. **Comparing hashes incorrectly.** Hashes are byte arrays — compare as big-endian integers (most significant byte first). A lexicographic comparison on bytes is the same as big-endian integer comparison only if bytes are in big-endian order.

5. **Skipping Merkle root validation.** A block with a fake Merkle root may have an invalid tx set. Verify the Merkle root matches the tx list.

6. **Allowing timestamps too far in the future.** A block with a far-future timestamp can be used to manipulate difficulty adjustment. Most protocols limit how far ahead a timestamp can be.

7. **Using "number of blocks" as chain weight.** The chain with the most blocks is not necessarily the heaviest. Use cumulative work.

8. **Not validating PoW on every block.** PoW validation is cheap (one or two hashes) — do it. Don't trust blocks from peers without verification.

9. **Mining with a single thread when parallelism is available.** PoW is embarrassingly parallel. Use multiple threads or GPUs (if the algorithm supports it).

10. **Homemade difficulty algorithms without testing.** A difficulty algorithm that doesn't respond correctly to hash power changes leads to unstable block times. Test against simulated hash power changes.
