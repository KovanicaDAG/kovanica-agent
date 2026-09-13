---
name: rust-mempool
description: Use when implementing a transaction mempool: tx arrival, validation, fee ordering, replacement, eviction policies, size limits, propagation, and integration with block building.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, mempool, transaction-pool, fee-ordering, replacement, eviction, validation, p2p]
    related_skills: [rust-utxo-ledger, rust-block-propagation, rust-consensus-pow, blockchain-fundamentals]
---

# Rust Mempool

## Overview

A mempool (transaction pool) is the buffer between transaction reception and block inclusion. It validates incoming transactions, stores them, orders them for block building (usually by fee), and handles eviction when the pool is full. The mempool must be fast, consistent across peers (ideally), and resistant to spam/flooding.

For UTXO chains, the mempool tracks spent/unspent outputs. For account chains, it tracks nonces and account states. The design differs but the core concerns are similar.

## When to Use

- Building a transaction pool for a new chain
- Designing fee-based ordering and replacement policies
- Handling tx replacement (RBF-style) or eviction
- Integrating a mempool with block building / consensus
- Dealing with tx validation, rate limiting, and spam resistance

**Don't use for:** consensus (mempool ≠ consensus — the pool is pre-consensus), or state finalization.

## Core Responsibilities

1. **Validation** — check signature, format, fee, inputs/outputs, double-spend, nonce, size, and any chain-specific rules before accepting.
2. **Storage** — keep valid transactions in memory, indexed for efficient lookup (by txid, by input spent status, by account/nonce).
3. **Ordering** — for block building, order by fee (rate = fee / size), or priority, or by consensus rules.
4. **Replacement** — allow a new transaction to replace an existing one (higher fee, same inputs, or same nonce for account chains).
5. **Eviction** — when the pool is full, evict low-fee or old transactions to make room.
6. **Propagation** — forward valid transactions to peers (P2P), optionally with compact representations or tx request protocols.
7. **Limits** — total pool size (by byte or tx count), per-account limits, rate limits per peer.

## UTXO Mempool Design

### Transaction Structure

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transaction {
    pub txid: TxId,          // hash of the tx
    pub inputs: Vec<TxInput>,
    pub outputs: Vec<TxOutput>,
    pub fee: u64,            // fee paid (sum inputs - sum outputs)
    pub size: usize,         // serialized size in bytes
    pub fee_rate: u64,       // fee per byte (or per weight unit)
}

#[derive(Debug, Clone)]
pub struct TxInput {
    pub outpoint: OutPoint,  // (txid, output_index) being spent
    pub signature: Vec<u8>,  // or script / witness
}

#[derive(Debug, Clone)]
pub struct TxOutput {
    pub value: u64,
    pub script: Vec<u8>,     // or address / locking script
}
```

### Pool Storage

```rust
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, RwLock};

pub struct Mempool {
    txs: HashMap<TxId, Transaction>,
    spent_outpoints: HashSet<OutPoint>,   // outpoints spent by pool txs
    by_fee_rate: Vec<TxId>,               // sorted by fee_rate descending
    max_size_bytes: usize,
    current_size_bytes: usize,
}
```

**Better index structure:** keep a `HashMap<TxId, Transaction>` for lookups, a `HashSet<OutPoint>` for double-spend detection, and a priority queue or sorted list for fee ordering.

### Validation Before Acceptance

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum MempoolError {
    #[error("tx already in pool")]
    AlreadyInPool,

    #[error("tx too large: {size} bytes")]
    TooLarge { size: usize },

    #[error("invalid fee: {fee}, required minimum {min_fee}")]
    InvalidFee { fee: u64, min_fee: u64 },

    #[error("double spend: outpoint {outpoint} already spent")]
    DoubleSpend { outpoint: OutPoint },

    #[error("input already spent by a pool tx")]
    InputSpent,

    #[error("signature verification failed")]
    InvalidSignature,

    #[error("tx rejected: {reason}")]
    Rejected { reason: String },
}

impl Mempool {
    pub fn accept(&mut self, tx: Transaction) -> Result<(), MempoolError> {
        // 1. Size check
        if tx.size > MAX_TX_SIZE {
            return Err(MempoolError::TooLarge { size: tx.size });
        }

        // 2. Fee check
        if tx.fee < self.min_fee {
            return Err(MempoolError::InvalidFee { fee: tx.fee, min_fee: self.min_fee });
        }

        // 3. Already in pool?
        if self.txs.contains_key(&tx.txid) {
            return Err(MempoolError::AlreadyInPool);
        }

        // 4. Double-spend check
        for input in &tx.inputs {
            if self.spent_outpoints.contains(&input.outpoint) {
                return Err(MempoolError::DoubleSpend { outpoint: input.outpoint });
            }
            if self.txs.values().any(|pool_tx| {
                pool_tx.inputs.iter().any(|i| i.outpoint == input.outpoint)
            }) {
                return Err(MempoolError::InputSpent);
            }
        }

        // 5. Signature verification
        verify_transaction(&tx)?;   // chain-specific

        // 6. Add to pool
        for input in &tx.inputs {
            self.spent_outpoints.insert(input.outpoint);
            for pool_tx in self.txs.values_mut() {
                pool_tx.inputs.retain(|i| i.outpoint != input.outpoint);
            }
        }

        self.txs.insert(tx.txid, tx.clone());
        self.current_size_bytes += tx.size;
        self.by_fee_rate.retain(|&id| id != tx.txid);   // remove old entry
        self.by_fee_rate.push(tx.txid);
        self.by_fee_rate.sort_by(|a, b| {
            self.txs[a].fee_rate.cmp(&self.txs[b].fee_rate)
        });

        // 7. Eviction if over limit
        self.evict_if_needed();

        Ok(())
    }
}
```

### Eviction Policy

```rust
impl Mempool {
    fn evict_if_needed(&mut self) {
        while self.current_size_bytes > self.max_size_bytes {
            // Evict lowest fee-rate tx
            if let Some(lowest_id) = self.by_fee_rate.pop() {
                let tx = self.txs.remove(&lowest_id).unwrap();
                self.current_size_bytes -= tx.size;
                // Return outpoints to available set
                for input in tx.inputs {
                    // Only remove from spent set if no other pool tx spends it
                    if !self.txs.values().any(|pt| pt.inputs.iter().any(|i| i.outpoint == input.outpoint)) {
                        // Actually we don't track "available" separately — we track "spent"
                        // Better: spent_outpoints is the set of all outpoints spent by ANY pool tx
                        // On eviction, we need to check if the outpoint is still spent
                    }
                }
            } else {
                break;
            }
        }
    }
}
```

**Improved design:** track `spent_outpoints` as the set of all outpoints currently spent by pool txs. On eviction, re-check if the evicted tx's outpoints are still spent by remaining txs. If not, remove from `spent_outpoints`.

### Replacement (RBF-style)

For UTXO chains with Replace-By-Fee:

```rust
impl Mempool {
    pub fn replace(&mut self, new_tx: Transaction) -> Result<(), MempoolError> {
        // Find txs in pool that conflict (share inputs) with new_tx
        let conflicting: Vec<TxId> = self.txs.iter()
            .filter(|(_, pool_tx)| {
                new_tx.inputs.iter().any(|ni| {
                    pool_tx.inputs.iter().any(|pi| pi.outpoint == ni.outpoint)
                })
            })
            .map(|(id, _)| id.clone())
            .collect();

        if conflicting.is_empty() {
            return self.accept(new_tx);
        }

        // Check replacement rules: new_tx must pay higher total fee than conflicting txs
        let conflicting_fee: u64 = conflicting.iter()
            .map(|&id| self.txs[&id].fee)
            .sum();

        if new_tx.fee <= conflicting_fee {
            return Err(MempoolError::Rejected { reason: "replacement fee too low".into() });
        }

        // Remove conflicting txs
        for id in &conflicting {
            let tx = self.txs.remove(id).unwrap();
            self.current_size_bytes -= tx.size;
            // recalc spent_outpoints...
        }

        self.accept(new_tx)
    }
}
```

## Account Mempool Design (Nonce-Based)

For account-model chains, the mempool tracks per-account nonces and ensures transactions are mined in nonce order.

```rust
use std::collections::{HashMap, BTreeMap};

pub struct AccountMempool {
    // nonce -> transaction (per account)
    account_txs: HashMap<Address, BTreeMap<Nonce, Transaction>>,
    // txid -> transaction (for lookup)
    txs: HashMap<TxId, Transaction>,
    max_size_bytes: usize,
    current_size_bytes: usize,
}

impl AccountMempool {
    pub fn accept(&mut self, tx: Transaction, sender: Address) -> Result<(), MempoolError> {
        let nonce = tx.nonce;

        // Check nonce ordering: there shouldn't be a gap
        let account_map = self.account_txs.entry(sender).or_default();

        // If there's already a tx at this nonce, it must be replaced (higher fee)
        if let Some(existing) = account_map.get(&nonce) {
            if tx.fee <= existing.fee {
                return Err(MempoolError::Rejected { reason: "replacement fee not higher".into() });
            }
            // Remove existing
            let old_tx = account_map.remove(&nonce).unwrap();
            self.txs.remove(&old_tx.txid);
            self.current_size_bytes -= old_tx.size;
        }

        // Check that nonce is consecutive (no gaps from the account's perspective)
        let lowest_nonce = account_map.keys().next().copied().unwrap_or(0);
        if nonce != lowest_nonce && nonce != lowest_nonce + 1 {
            // Allow some gaps for mempool, but block builder needs sequential
            // For strict chains, reject gaps
        }

        account_map.insert(nonce, tx.clone());
        self.txs.insert(tx.txid, tx);
        self.current_size_bytes += tx.size;

        self.evict_if_needed();
        Ok(())
    }

    pub fn get_ready_tx(&self, sender: &Address) -> Option<Transaction> {
        // Get the lowest nonce for the account (next to be mined)
        self.account_txs.get(sender)
            .and_then(|map| map.values().next().cloned())
    }
}
```

## Fee Ordering for Block Building

For UTXO pools, the block builder selects txs by fee rate (fee per byte or per weight). The classic knapsack-style selection:

```rust
use std::collections::BinaryHeap;

#[derive(Eq, PartialEq, Ord, PartialOrd)]
struct FeeRateTx {
    fee_rate: u64,
    txid: TxId,
}

impl Mempool {
    pub fn select_for_block(&self, max_weight: u64) -> Vec<TxId> {
        let mut selected = Vec::new();
        let mut weight_used = 0u64;

        // Use a max-heap by fee_rate
        let mut heap: BinaryHeap<FeeRateTx> = self.by_fee_rate.iter()
            .map(|&id| FeeRateTx {
                fee_rate: self.txs[&id].fee_rate,
                txid: id,
            })
            .collect();

        while let Some(FeeRateTx { txid, fee_rate }) = heap.pop() {
            let tx = &self.txs[&txid];
            if weight_used + tx.weight <= max_weight {
                // Check that all inputs are still unspent (not spent by already-selected txs)
                if tx.inputs.iter().all(|i| !selected_outpoints.contains(&i.outpoint)) {
                    selected.push(txid);
                    weight_used += tx.weight;
                    for i in &tx.inputs {
                        selected_outpoints.insert(i.outpoint);
                    }
                }
            }
        }

        selected
    }
}
```

**Note:** This greedy approach (highest fee rate first) is not optimal for the knapsack (some lower-fee txs may fit better), but it's the standard approximation. Exact optimization is NP-hard for arbitrary tx sets.

## Rate Limiting and Spam Resistance

```rust
use std::collections::HashMap;
use std::time::{Instant, Duration};

pub struct RateLimiter {
    peer_tx_counts: HashMap<PeerId, (Instant, usize)>,
    window: Duration,
    max_tx_per_window: usize,
}

impl RateLimiter {
    pub fn check(&mut self, peer: PeerId) -> bool {
        let (since, count) = self.peer_tx_counts.entry(peer).or_insert((Instant::now(), 0));
        if since.elapsed() > self.window {
            *since = Instant::now();
            *count = 0;
        }
        if *count >= self.max_tx_per_window {
            return false;   // rate limited
        }
        *count += 1;
        true
    }
}
```

## P2P Propagation

Valid transactions are forwarded to peers. Patterns:

- **Flood:** send to all peers (simple, but amplifies bandwidth).
- **Tx request / compact block:** send block/header + tx hashes, peers request missing txs.
- **Inv + getdata:** advertise txs via `inv` messages, peers request with `getdata`.

```rust
pub struct TxPropagator {
    peers: Vec<PeerId>,
    inv_queue: Vec<TxId>,
}

impl TxPropagator {
    pub fn on_new_tx(&mut self, txid: TxId) {
        self.inv_queue.push(txid);
    }

    pub fn broadcast(&mut self) {
        for txid in &self.inv_queue {
            for peer in &self.peers {
                self.send_inv(peer, *txid);
            }
        }
        self.inv_queue.clear();
    }
}
```

## Consistency Across Peers

Mempools across nodes diverge naturally. Strategies for consistency:
- **Re-broadcast:** periodically re-announce txs to keep them in peer pools.
- **Tx reconciliation:** exchange tx hashes with peers, request missing ones.
- **Random peer selection:** avoid sending to all peers every time; send to a subset.

## Testing the Mempool

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_double_spend_rejected() {
        let mut pool = Mempool::new(MAX_SIZE);
        let tx1 = make_tx(vec![outpoint1], vec![output1]);
        let tx2 = make_tx(vec![outpoint1], vec![output2]);   // same input

        pool.accept(tx1).unwrap();
        assert!(pool.accept(tx2).is_err());
    }

    #[test]
    fn test_fee_ordering() {
        let mut pool = Mempool::new(MAX_SIZE);
        pool.accept(make_tx_with_fee(10)).unwrap();
        pool.accept(make_tx_with_fee(100)).unwrap();
        pool.accept(make_tx_with_fee(50)).unwrap();

        let selected = pool.select_for_block(MAX_WEIGHT);
        assert_eq!(selected[0], tx_with_100_fee.txid);   // highest fee first
    }

    #[test]
    fn test_eviction() {
        let mut pool = Mempool::with_limit(SMALL_LIMIT);
        // fill pool
        for i in 0..100 {
            pool.accept(make_tx_with_fee(i as u64)).unwrap();
        }
        // low-fee txs should be evicted
        assert!(!pool.contains(&low_fee_txid));
    }
}
```

## Verification Checklist

- [ ] Can define a transaction structure with inputs, outputs, fee, and size
- [ ] Can validate a transaction before pool acceptance (signature, fee, size, double-spend)
- [ ] Can track spent outpoints and detect double-spends
- [ ] Can order transactions by fee rate for block building
- [ ] Can implement eviction when the pool exceeds size limits
- [ ] Can implement replacement (RBF) with fee comparison
- [ ] Can implement nonce-based account mempool with per-account ordering
- [ ] Can implement rate limiting per peer
- [ ] Can forward transactions to peers (basic propagation)
- [ ] Can write tests covering double-spend, fee ordering, eviction, replacement

## Common Pitfalls

1. **Not detecting double-spends across pool txs.** Two txs that spend the same outpoint — both can't be in the pool. Track spent outpoints.

2. **Not tracking spent outpoints on eviction.** When evicting a tx, its outpoints become available again — but only if no other pool tx spends them. Track per-outpoint refcounts or re-check.

3. **Fee ordering without checking input availability.** Selecting a high-fee tx whose inputs are spent by a lower-fee tx already selected breaks the block. Check input availability during selection.

4. **Not enforcing transaction size limits.** Large txs can bloat the pool and blocks. Set a max size.

5. **Accepting txs without fee checks.** Free txs spam the pool. Enforce a minimum fee or rate.

6. **Not ordering by fee for block building.** Without fee ordering, the block builder may include low-fee txs before high-fee ones, losing revenue.

7. **Not rate-limiting peer submissions.** A peer can flood the pool with txs. Rate-limit per peer.

8. **Ignoring transaction replacement rules.** If RBF is allowed, enforce the fee bump rule. If not, reject conflicting txs.

9. **Not re-validating pool txs after chain reorg.** On a reorg, the mempool may contain txs that are now invalid (inputs spent by the new chain). Prune or re-validate.

10. **Assuming mempool is consistent across nodes.** It's not. Design propagation and reconciliation to minimize divergence, but accept that it happens.
