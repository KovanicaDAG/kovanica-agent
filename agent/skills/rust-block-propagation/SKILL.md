---
name: rust-block-propagation
description: Use when designing block and transaction propagation in a P2P network: compact block relay, tx requests, block templates, header-first propagation, network bandwidth tradeoffs, and integration with the mempool.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, blockchain, p2p, block-propagation, compact-blocks, tx-requests, header-first, network, mempool]
    related_skills: [rust-p2p-networking, rust-mempool, rust-consensus-pow, rust-consensus-pos]
---

# Rust Block Propagation

## Overview

Block propagation is how new blocks travel from the miner/validator to the rest of the network. The design affects network latency, orphan rate, bandwidth usage, and ultimately the chain's security (slow propagation → more orphans → centralization pressure). Modern protocols use header-first propagation, compact blocks, and tx request mechanisms to minimize bandwidth.

This skill covers the network layer of block propagation, not the consensus rules for what makes a valid block (see rust-consensus-* skills).

## When to Use

- Building a P2P layer for a new blockchain
- Designing block relay to minimize latency and bandwidth
- Implementing compact block relay or tx request protocols
- Integrating block propagation with the mempool and block validation
- Understanding why header-first propagation matters for orphan rate

**Don't use for:** consensus validation of blocks (separate skill), or transaction pool logic (separate skill, but propagation integrates with it).

## Propagation Modes

### Full Block Propagation

Send the full block (header + all txs) to peers. Simple, but bandwidth-intensive for large blocks.

```
Peer A (miner) → sends full block to Peer B
Peer B validates, stores, forwards to peers
```

**Drawbacks:** every peer downloads the full block, even if it already has most of the txs in its mempool.

### Header-First Propagation

Send the block header first, then the body. Peers can start validating the header (PoW, PoS, consensus rules) before downloading the body.

```
1. Peer A sends header to Peer B
2. Peer B validates header (PoW, nonce, merkle root format, etc.)
3. If header valid, Peer B requests the body (or the missing txs)
4. Peer A sends body / missing txs
```

**Benefit:** peers can reject invalid blocks early (bad PoW, wrong parent, etc.) without downloading the full body.

### Compact Block Relay (BIP-152 style)

Send a compact representation of the block: header + short tx hashes (or indexes). The receiver already has most of the txs in its mempool — it reconstructs the block from mempool txs, then requests missing ones.

```
1. Sender sends compact block: header + list of tx hashes
2. Receiver reconstructs block from mempool (matches hashes to mempool txs)
3. Receiver identifies missing txs, requests them
4. Sender sends missing txs
5. Receiver assembles full block, validates, forwards
```

**Benefit:** much less bandwidth when the mempool is full (most txs are already known). Worst case (empty mempool), still needs to request all txs.

### Tx Request / Extended Compact Blocks

Similar to compact blocks but with more efficient tx request mechanisms. The receiver sends a list of tx hashes it needs, the sender responds with those txs. This is used in modern implementations (e.g., Kaspa's DGP, Bitcoin's BIP-152 + Compact Blocks).

## Header Structure

A block header typically contains:

```rust
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BlockHeader {
    pub version: u32,
    pub previous_hash: [u8; 32],   // parent block hash
    pub merkle_root: [u8; 32],     // tx Merkle root
    pub timestamp: u64,
    pub difficulty: u64,           // or PoS field, or VRF output
    pub nonce: u64,                // or mix hash, or other PoW field
    // For PoS/consensus-specific:
    pub validator: Address,        // who proposed the block
    pub signature: Vec<u8>,        // block signature (PoS)
    pub height: u64,               // block height (optional, can be derived)
}
```

The header is small (tens to hundreds of bytes) and is the unit of header-first propagation.

## Compact Block Format

A compact block minimizes the data sent over the network:

```rust
#[derive(Debug, Serialize, Deserialize)]
pub struct CompactBlock {
    pub header: BlockHeader,
    pub tx_hashes: Vec<TxId>,       // short hashes of txs in the block (in order)
    // Optional: tx indexes for mempool matching
}
```

The receiver matches `tx_hashes` against its mempool. Txs that match are already available; only the missing ones need to be requested.

**Size savings:** a compact block is typically ~10-100KB vs a full block of 1-10MB+ (depending on tx count).

## Block Validation During Propagation

Validation happens in stages:

1. **Header validation (fast):** PoW check, parent exists, timestamp rules, difficulty/merkle root format.
2. **Partial body validation (if compact):** match tx hashes to mempool, check that all txs are known or requested.
3. **Full validation:** once the full block is assembled, validate all txs (signatures, double-spends, fees, scripts).

**Staged validation:** header-first + compact blocks allow peers to reject bad blocks at the header stage, saving bandwidth.

```rust
pub fn validate_header(header: &BlockHeader, tip: &BlockTip) -> Result<(), BlockError> {
    // Check parent exists
    if !tip.contains(&header.previous_hash) {
        return Err(BlockError::UnknownParent);
    }

    // Check PoW (if applicable)
    if !check_pow(&header) {
        return Err(BlockError::InvalidPow);
    }

    // Check timestamp (not too far in the future, not too old)
    if header.timestamp > current_time + MAX_TIME_DRIFT {
        return Err(BlockError::TimestampTooFar);
    }

    // Check merkle root format (hash is 32 bytes, etc.)
    // (full merkle root validation requires the tx list)

    Ok(())
}
```

## P2P Message Flow

### Block Relay

```
1. Miner creates block
2. Miner sends `block` message (or `headers` + `compact_block`) to connected peers
3. Peer receives, validates header
4. If header valid:
   a. If full block: download body, validate, store, forward
   b. If compact: reconstruct from mempool, request missing txs, validate, store, forward
5. Forward to peers (with rate limiting / deduplication)
```

### Tx Relay (from mempool to block)

```
1. Tx arrives from network or local submission
2. Validate tx, add to mempool
3. Broadcast tx to peers (inv/announce, or compact tx relay)
4. When a block is mined/validated, the tx is removed from the mempool (included)
```

### Deduplication and Flood Control

To avoid amplifying blocks/txs across the network:

- **Deduplication:** don't forward a block/tx to a peer that already has it. Track what's been sent to whom.
- **Flood limits:** limit how many peers a new block/tx is forwarded to at once.
- **Rebroadcast:** periodically rebroadcast blocks/txs to keep them in peer mempools (especially for compact blocks where txs may be evicted).

```rust
use std::collections::{HashMap, HashSet};

pub struct FloodControl {
    sent_blocks: HashMap<BlockId, HashSet<PeerId>>,   // which peers have been sent which block
    sent_txs: HashMap<TxId, HashSet<PeerId>>,
}

impl FloodControl {
    pub fn should_send_block(&self, block_id: &BlockId, peer: &PeerId) -> bool {
        !self.sent_blocks.get(block_id).map_or(false, |peers| peers.contains(peer))
    }

    pub fn mark_sent(&mut self, block_id: &BlockId, peer: &PeerId) {
        self.sent_blocks.entry(block_id.clone()).or_default().insert(peer.clone());
    }
}
```

## Bandwidth Optimization

### Techniques

| Technique | Benefit | Cost |
|---|---|---|
| Header-first | Fast rejection of invalid blocks | Extra round-trip for body |
| Compact blocks | Much less bandwidth for in-mempool txs | Receiver must have txs in mempool |
| Tx requests | Only fetch missing txs | Extra messages |
| Tx compression | Smaller tx payloads | CPU for compression/decompression |
| Block template optimization | Smaller blocks (less waste) | Miner/validator optimization |

### Block Size / Weight Limits

Blocks have limits (size, weight, tx count) set by consensus. Propagation design must respect these — a block that's too large takes longer to propagate and increases orphan risk.

```rust
pub const MAX_BLOCK_SIZE: usize = 4_000_000;   // example: 4 MB
pub const MAX_BLOCK_WEIGHT: u64 = 4_000_000;   // if using weight-based limits

fn is_block_too_large(tx_count: usize, avg_tx_size: usize) -> bool {
    tx_count * avg_tx_size > MAX_BLOCK_SIZE
}
```

## Orphan Block Handling

An orphan block is a block whose parent isn't known yet (e.g., received before the parent due to network latency).

```rust
pub struct OrphanPool {
    orphans: HashMap<BlockId, BlockHeader>,   // headers of orphan blocks
    // Could also store partial bodies for compact blocks
}

impl OrphanPool {
    pub fn add_orphan(&mut self, header: BlockHeader) {
        self.orphans.insert(header.hash(), header);
    }

    pub fn resolve_orphan(&mut self, block_id: &BlockId) -> Option<BlockHeader> {
        // When the parent arrives, check if any orphans have this parent
        self.orphans.remove(block_id)
    }
}
```

Orphan blocks are stored until their parent arrives, then they're processed (validated, stored, forwarded).

## Integration with Mempool

When a block is accepted:

1. **Remove included txs from mempool.** Txs in the block are no longer pending.
2. **Re-evaluate txs that depended on removed txs.** In UTXO chains, txs that spent outputs now included in the block are invalid — remove them too.
3. **Restore evicted txs?** If a tx was evicted from the mempool but is now included in a block, it's fine — it's no longer needed in the pool.

```rust
pub fn on_block_accepted(&mut self, block: &Block) {
    for tx in &block.txs {
        self.mempool.remove(&tx.txid);
        // For UTXO: re-evaluate txs that spend outputs now spent by this block
        for dependent_tx in self.mempool.get_dependents(&tx.inputs) {
            if self.mempool.is_double_spend(&dependent_tx) {
                self.mempool.remove(&dependent_tx.txid);
            }
        }
    }
}
```

## Testing Propagation

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_first_rejects_invalid_pow() {
        let header = make_header_with_bad_pow();
        assert!(validate_header(&header, &tip).is_err());
    }

    #[test]
    fn test_compact_block_reconstruction() {
        let mut mempool = Mempool::new();
        // Add txs to mempool
        for tx in test_txs {
            mempool.accept(tx).unwrap();
        }

        let compact = CompactBlock { header, tx_hashes: ... };
        let block = reconstruct_block(&compact, &mempool).unwrap();
        assert_eq!(block.txs.len(), compact.tx_hashes.len());
    }

    #[test]
    fn test_duplicate_block_not_forwarded() {
        let mut flood = FloodControl::new();
        let block_id = BlockId::new();
        let peer = PeerId::new();

        assert!(flood.should_send_block(&block_id, &peer));
        flood.mark_sent(&block_id, &peer);
        assert!(!flood.should_send_block(&block_id, &peer));
    }
}
```

## Verification Checklist

- [ ] Can describe header-first propagation and why it reduces bandwidth for invalid blocks
- [ ] Can describe compact block relay and how the receiver reconstructs the block
- [ ] Can define a block header and a compact block format
- [ ] Can implement staged validation (header first, then body)
- [ ] Can implement tx request logic for missing txs in a compact block
- [ ] Can implement flood control (deduplication of forwarded blocks/txs)
- [ ] Can handle orphan blocks (store, resolve when parent arrives)
- [ ] Can integrate block acceptance with mempool cleanup (remove included txs, re-evaluate dependents)
- [ ] Understands the relationship between block size limits and propagation latency

## Common Pitfalls

1. **Sending full blocks always.** Wastes bandwidth when peers already have most txs. Use compact blocks or header-first.

2. **Not validating headers before requesting bodies.** An attacker can send invalid headers + large bodies, wasting the receiver's bandwidth. Validate header first.

3. **Not deduplicating forwarded blocks.** A block can be forwarded to the same peer multiple times, wasting bandwidth. Track sent blocks per peer.

4. **Not handling orphan blocks.** If a block arrives before its parent, it must be stored as an orphan and resolved when the parent arrives. Otherwise, the block is dropped and the chain stalls.

5. **Not cleaning up the mempool on block acceptance.** Txs included in a block should be removed from the mempool. Txs that spent now-spent outputs should also be removed.

6. **Assuming the mempool is consistent across peers.** It's not. Compact block reconstruction depends on the receiver's mempool — if it's missing txs, they must be requested. Plan for that.

7. **Broadcasting blocks to all peers at once.** Can cause a stampede. Use a subset or rate-limit forwarding.

8. **Not respecting block size limits in propagation.** A block that exceeds the limit is invalid. Check before forwarding.

9. **Ignoring re-orgs.** On a re-org, the mempool may contain txs that conflict with the new chain. Clean up the mempool.

10. **Not rate-limiting block/tx announcements.** An attacker can flood the network with invalid blocks/txs. Rate-limit announcements and validate before forwarding.
