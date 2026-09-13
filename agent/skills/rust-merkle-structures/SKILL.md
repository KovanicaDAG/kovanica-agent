---
name: rust-merkle-structures
description: Use when implementing Merkle trees and variants: Merkle proofs (inclusion/exclusion), Merkle Mountain Ranges (MMR), sparse Merkle trees (SMT), and state roots for blockchain state.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, blockchain, merkle, merkle-proof, MMR, SMT, state-root, inclusion-proof, exclusion-proof]
    related_skills: [rust-crypto-primitives, rust-consensus-ghostdag, rust-account-ledger, rust-utxo-ledger]
---

# Rust Merkle Structures

## Overview

Merkle structures are hash-based data structures that summarize a set of items into a single root hash, with compact proofs of inclusion (or exclusion) for individual items. They're fundamental to blockchain: transaction Merkle trees in blocks, state trees (MPT, SMT, MMR), and light-client proofs.

This skill covers the common Merkle tree variants and their proof systems. The choice of structure depends on the use case: inclusion proofs for a static set (Merkle tree), a growing log (MMR), a key-value map (sparse Merkle tree), or a combination.

## When to Use

- Building a transaction Merkle tree for block headers
- Implementing light-client proofs (tx inclusion, state inclusion)
- Designing a state tree (MPT for Ethereum-style, SMT for ZK-friendly, MMR for append-only logs)
- Providing inclusion/exclusion proofs for a set of items
- Building a commitment scheme for a set or map

**Don't use for:** consensus rules (Merkle root is a commitment, but consensus logic is separate), or proof-of-work (hashes for PoW are separate from Merkle structure).

## Standard Merkle Tree (Binary, Append-Only)

### Construction

A binary Merkle tree takes N leaves (hashes), pairs them up, hashes each pair to form the parent, and repeats until one root remains.

```rust
use sha2::{Sha256, Digest};
use merkle::MerkleTree;   // or build manually

// Using the `merkle` crate
use merkle::Hasher;

let leaves: Vec<Vec<u8>> = vec![
    vec![1, 2, 3],
    vec![4, 5, 6],
    vec![7, 8, 9],
    vec![10, 11, 12],
];

let tree = MerkleTree::from_leaves::<Sha256, _>(&leaves).unwrap();
let root = tree.root().unwrap();
```

### Manual Construction

```rust
pub fn compute_merkle_root(leaves: &[&[u8]]) -> Vec<u8> {
    if leaves.is_empty() {
        return vec![0u8; 32];
    }

    let mut current: Vec<Vec<u8>> = leaves.iter().map(|l| l.to_vec()).collect();

    while current.len() > 1 {
        let mut next = Vec::with_capacity((current.len() + 1) / 2);
        for chunk in current.chunks(2) {
            if chunk.len() == 2 {
                let mut hasher = Sha256::new();
                hasher.update(&chunk[0]);
                hasher.update(&chunk[1]);
                next.push(hasher.finalize().to_vec());
            } else {
                // Odd leaf — duplicate it (Bitcoin convention) or handle differently
                next.push(chunk[0].clone());
            }
        }
        current = next;
    }

    current[0].clone()
}
```

**Odd-leaf conventions:**
- **Bitcoin:** duplicate the last leaf (hash(tx, tx) for the odd parent).
- **Ethereum MPT:** uses a different structure (see sparse Merkle tree below).
- **Generic:** the convention must be specified.

### Merkle Proof (Inclusion)

A Merkle proof for leaf `i` consists of the sibling hashes along the path from leaf to root, plus the leaf index and total leaf count.

```rust
#[derive(Debug, Clone)]
pub struct MerkleProof {
    pub leaf: Vec<u8>,
    pub leaf_index: usize,
    pub total_leaves: usize,
    pub siblings: Vec<Vec<u8>>,   // siblings from leaf to root (excludes the leaf itself)
}

impl MerkleProof {
    pub fn verify(&self, root: &[u8]) -> bool {
        let mut hash = self.leaf.clone();

        for (depth, sibling) in self.siblings.iter().enumerate() {
            let bit = (self.leaf_index >> depth) & 1;
            let mut hasher = Sha256::new();
            if bit == 0 {
                hasher.update(&hash);
                hasher.update(sibling);
            } else {
                hasher.update(sibling);
                hasher.update(&hash);
            }
            hash = hasher.finalize().to_vec();
        }

        hash == root
    }
}
```

**Proof generation:**

```rust
pub fn generate_proof(leaves: &[Vec<u8>], index: usize) -> MerkleProof {
    let mut proof = MerkleProof {
        leaf: leaves[index].clone(),
        leaf_index: index,
        total_leaves: leaves.len(),
        siblings: Vec::new(),
    };

    let mut layer: Vec<Vec<u8>> = leaves.to_vec();
    let mut idx = index;

    while layer.len() > 1 {
        let mut next_layer = Vec::new();
        for i in (0..layer.len()).step_by(2) {
            if i + 1 < layer.len() {
                let sibling_idx = if idx == i { i + 1 } else { i };
                proof.siblings.push(layer[sibling_idx].clone());

                let mut hasher = Sha256::new();
                hasher.update(&layer[i]);
                hasher.update(&layer[i + 1]);
                next_layer.push(hasher.finalize().to_vec());
            } else {
                next_layer.push(layer[i].clone());
                if idx == i {
                    proof.siblings.push(layer[i].clone());
                }
            }
        }
        layer = next_layer;
        if idx % 2 == 0 {
            idx /= 2;
        } else {
            idx = idx / 2;
        }
    }

    proof
}
```

## Merkle Mountain Range (MMR)

MMR is a Merkle structure for an append-only log where you can prove inclusion of any element without recomputing the whole tree. Used in Bitcoin (BIP-158, compact block filters), and in some state commitment schemes.

### Concept

An MMR is a sequence of Merkle trees (peaks) where each new element extends the structure. The peaks form a "mountain range" — you can prove an element is in the MMR by providing the path to the peak it belongs to.

```rust
use merkle_mountain_range::MerkleMountainRange;

let mut mmr = MerkleMountainRange::new();
for leaf in leaves {
    mmr.push(leaf).unwrap();
}

let root = mmr.roots().last().unwrap().clone();
let proof = mmr.prove(leaf_index).unwrap();
proof.verify(&root, &leaf).unwrap();
```

### MMR Use Cases

- **Compact block filters (BIP-158):** Bloom filters or Golomb-coded sets for SPV clients.
- **Append-only logs:** Certificate Transparency-style logs.
- **State commitments in growing chains:** where you don't want to rebuild the whole tree on each block.

## Sparse Merkle Tree (SMT)

A sparse Merkle tree is a Merkle tree over a key space (e.g., 2^256 slots for Ethereum addresses). Each slot is a leaf; empty slots are a special "empty" value. This enables efficient proofs of non-inclusion (a key is not in the tree).

### Structure

```rust
use std::collections::HashMap;

pub struct SparseMerkleTree {
    depth: u32,           // tree depth (e.g., 256 for 256-bit keys)
    empty_value: Vec<u8>, // pre-computed empty node hash at each level
    nodes: HashMap<Vec<u8>, Vec<u8>>,  // node hash -> children (or precomputed)
    root: Vec<u8>,
}
```

**Key idea:** in a full binary Merkle tree of depth D, there are 2^D leaves. In an SMT, most leaves are empty. The tree is sparse — only non-empty leaves are stored. Proofs must include the empty-sibling hashes (which are deterministic and precomputed).

### SMT Proof

```rust
pub struct SmtProof {
    pub key: Vec<u8>,          // the queried key (e.g., 256-bit address)
    pub value: Option<Vec<u8>>, // the value at the key (None if empty)
    pub siblings: Vec<(Vec<u8>, bool)>,  // (sibling_hash, is_left_sibling)
}
```

**Proof verification:** walk from leaf to root, using the key bits to decide which sibling to hash with. Empty nodes use the precomputed empty value.

### SMT vs MPT (Ethereum)

- **SMT:** binary tree over a fixed key space, empty slots are a known value. Good for ZK-friendly designs (Poseidon-friendly).
- **MPT (Merkle Patricia Trie):** Ethereum's state tree. Combines a Merkle tree with a Patricia trie (radix tree) for efficient key-value storage and compaction. More complex but space-efficient for sparse data.

### SMT in Rust

```toml
[dependencies]
sparse_merkle_tree = "0.1"   # example crate, or implement manually
# Or build with sha2 + manual node management
```

For ZK-friendly SMTs, use a hash function friendly to circuits (Poseidon, MiMC) rather than SHA-256.

## Merkle Proofs for State

### UTXO Set Proofs

For a UTXO-based chain, a light client can request a Merkle proof that a particular output is in the UTXO set (if the UTXO set is committed to a Merkle tree).

```rust
pub struct UtxoProof {
    pub outpoint: OutPoint,
    pub utxo: Utxo,
    pub merkle_proof: MerkleProof,   // proof that utxo is in the UTXO set tree
}
```

### Account State Proofs

For an account-based chain with a Merkle-patricia-trie or SMT over account state:

```rust
pub struct AccountProof {
    pub address: Address,
    pub account_state: AccountState,
    pub proof: SmtProof,   // or MPT proof
}
```

Light clients verify these proofs against a trusted state root (e.g., from a block header).

## Inclusion vs Exclusion Proofs

- **Inclusion proof:** proves an item is in the set/tree. Standard Merkle proof.
- **Exclusion proof:** proves an item is NOT in the set/tree. For a standard Merkle tree, there's no direct exclusion proof — you can only prove inclusion of a specific leaf. For SMTs, an exclusion proof shows that a key maps to an empty leaf (proven by the SMT proof returning None for that key).

For standard Merkle trees, exclusion is harder: you need to prove that a given leaf index has a different value than the claimed one, and that the tree root matches. This works if you know the total leaf count and the leaf positions are fixed.

## State Roots in Block Headers

Block headers often include a state root (Merkle root of the state tree). This allows light clients to verify state without downloading the full state.

```rust
#[derive(Debug, Serialize, Deserialize)]
pub struct BlockHeader {
    pub previous_hash: [u8; 32],
    pub merkle_root: [u8; 32],   // tx Merkle root
    pub state_root: [u8; 32],    // state tree root (MPT, SMT, etc.)
    pub timestamp: u64,
    pub nonce: u64,
    pub difficulty: u64,
}
```

A light client verifies a state proof by:
1. Verifying the block header (PoW, PoS, or consensus).
2. Verifying the state proof against the state root in the header.
3. Trusting that the header is part of the canonical chain (via consensus).

## Verification Checklist

- [ ] Can construct a binary Merkle tree from leaves and compute the root
- [ ] Can generate and verify a Merkle inclusion proof
- [ ] Understands odd-leaf handling conventions (duplication vs other)
- [ ] Can explain the MMR concept and when it's preferred over a full Merkle tree
- [ ] Can explain the SMT concept and how exclusion proofs work
- [ ] Knows the difference between SMT and MPT and their tradeoffs
- [ ] Can integrate a state root into a block header
- [ ] Understands that light-client proofs require a trusted state root (from a verified block header)

## Common Pitfalls

1. **Not specifying odd-leaf handling.** Different conventions produce different roots for the same leaves. Specify.

2. **Using different hash functions for leaves vs internal nodes.** Must be consistent or specified. Bitcoin uses double-SHA-256 for txids, then single-SHA-256 for the Merkle tree.

3. **Not including the leaf index in the proof.** Without the index, the verifier doesn't know which sibling is on the left vs right, so the proof verification is ambiguous.

4. **Assuming exclusion proofs for standard Merkle trees.** Standard Merkle trees don't have direct exclusion proofs — you can only prove inclusion of a specific leaf. For exclusion, use SMTs or other structures.

5. **Using SHA-256 in SMTs for ZK applications.** SHA-256 is expensive in ZK circuits. Use a ZK-friendly hash (Poseidon, MiMC) for SMTs that will be used in ZK proofs.

6. **Not precomputing empty node hashes in SMTs.** The empty node hash at each level must be precomputed and used in proofs. Otherwise, the verifier can't distinguish an empty subtree from a missing one.

7. **Including the leaf value in the proof but not the leaf index.** The same sibling hashes can prove different leaves (at different indices). The index disambiguates.

8. **Assuming the Merkle root commits to the order of leaves.** In some constructions, the order matters (left/right in pairs). In others, it doesn't. Specify.

9. **Using a Merkle tree for key-value mapping without a sparse structure.** A dense Merkle tree over a key space wastes space. SMTs or MPTs are more efficient for sparse data.

10. **Not verifying the block header before trusting the state root.** A state proof is only as trustworthy as the block header it commits to. Verify the header's consensus validity first.
