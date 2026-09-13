---
name: rust-consensus-ghostdag
description: Use when implementing GHOSTDAG consensus (Kaspa-style BlockDAG): block DAG structure, k-cluster selection, blue/red colouring, blue score / cumulative difficulty, mergeset, and linearization into a canonical order.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [blockchain, GHOSTDAG, BlockDAG, k-cluster, blue-score, mergeset, colouring, Kaspa, linearization]
    related_skills: [blockchain-fundamentals, rust-consensus-pow, rust-merkle-structures, rust-block-propagation]
---

# Rust GHOSTDAG Consensus

## Overview

GHOSTDAG is a consensus protocol for a BlockDAG (a directed acyclic graph of blocks, where each block references multiple parents). It was introduced by Kaspa. Unlike a longest-chain PoW where only one parent is referenced, in a BlockDAG each block points to multiple previous blocks — typically the top of the current DAG. GHOSTDAG's job is to decide which blocks are "blue" (part of the canonical chain) and which are "red" (excluded), using a k-cluster coloring algorithm and a blue score proportional to the cumulative work.

This is a complex, consensus-critical algorithm. The coloring and k-cluster computation must be deterministic and adversarial-resistant. Do not implement from memory — reference the Kaspa specification and test against known DAGs.

## When to Use

- Implementing a BlockDAG-based consensus (Kaspa-style)
- Selecting the canonical set of blocks from a DAG
- Computing blue score / cumulative work
- Ordering blocks into a linear sequence for state application
- Understanding mergesets and how they affect blue/red colouring

**Don't use for:** chain-based PoW (use the PoW skill), PoS BFT (use the PoS skill), or any consensus that isn't a BlockDAG with k-cluster colouring.

## BlockDAG Structure

### Blocks and References

```rust
#[derive(Debug, Clone)]
struct Block {
    hash: Hash,
    header: BlockHeader,
    prev_hashes: Vec<Hash>,   // references to parent blocks (typically 2 in Kaspa)
    // transactions, etc.
}

#[derive(Debug, Clone)]
struct BlockDAG {
    blocks: HashMap<Hash, Block>,
    // block_order is computed by GHOSTDAG, not stored as a simple chain
}
```

Each block (except the genesis) references one or more previous blocks. In Kaspa, each block references the current tip(s) — the latest blocks in the DAG. This creates a DAG, not a chain.

### DAG vs Chain

| Property | Chain (PoW) | BlockDAG (GHOSTDAG) |
|---|---|---|
| Parent references | 1 (the previous block) | 2 or more (the current tips) |
| Structure | Linear chain | DAG |
| Canonical selection | Heaviest chain (cumulative work) | GHOSTDAG blue set (k-cluster) |
| Forks | Orphaned branches | Red blocks (referenced but excluded) |
| Throughput | Limited by block time × block size | Higher (parallel block creation) |

## k-Cluster and Colouring

### The Concept

GHOSTDAG colours blocks blue or red based on their position in the DAG and a parameter k (the cluster size). The algorithm:

1. Order blocks by their "blue point" (a reference point in the DAG).
2. For each block, consider the set of blocks within distance k (in the ordering) — that's the k-cluster.
3. The block is blue if its work contribution outweighs the work in the red blocks of its k-cluster; otherwise it's red.

The exact algorithm is more subtle: it processes blocks in a specific order (by their reference to earlier blocks), maintains the blue set, and for each new block, checks whether including it would make too many blocks red in its cluster. If so, it's red.

### Simplified Conceptual Flow

```rust
// Pseudocode — NOT a correct implementation; reference Kaspa spec
fn colour_dag(blocks: &[Block], k: usize) -> Vec<Colour> {
    // Order blocks by their "blue point" (some reference order)
    let ordered = order_by_blue_point(blocks);

    let mut blue_set = vec![];
    let mut colours = vec![];

    for block in ordered {
        let cluster = blocks_within_k(block, &ordered, k);
        let red_work_in_cluster = cluster.iter()
            .filter(|b| is_red(*b, &colours))
            .map(|b| work(b))
            .sum();

        if work(block) > red_work_in_cluster {
            colours.push(Colour::Blue);
            blue_set.push(block);
        } else {
            colours.push(Colour::Red);
        }
    }

    colours
}
```

**This is NOT a working implementation.** The actual GHOSTDAG algorithm uses a more precise definition of the cluster, the blue point, and the work comparison. Do not use this as a reference.

### The Blue Score

The blue score is the cumulative work of all blue blocks. It's used as the chain weight — the DAG with the highest blue score is canonical.

```rust
fn blue_score(blue_blocks: &[Block]) -> u128 {
    blue_blocks.iter().map(|b| work(b)).sum()
}
```

In a fork situation (two competing DAGs), the one with the higher blue score wins.

## Mergeset

A block's mergeset is the set of blocks that are "merged" into the DAG by this block — essentially, the blocks that this block references and that become part of the DAG through this block.

In Kaspa, a block's mergeset includes:
- The blocks it directly references (its parents).
- The blocks those parents reference (transitively, but limited by the DAG structure).

The mergeset is used in colouring: when a block is added, its mergeset is considered for the k-cluster computation.

```rust
fn mergeset(block: &Block, dag: &BlockDAG) -> Vec<Hash> {
    // Direct parents
    let mut set = block.prev_hashes.clone();
    // Also include the parents' mergesets? (depends on the exact definition)
    // ...
    set
}
```

## Linearization

The blue set isn't a linear chain — it's a set of blocks. To apply state, GHOSTDAG linearizes the blue blocks into an order:

1. Sort blue blocks by their "blue point" (or by a deterministic ordering derived from the DAG structure and the blue colouring).
2. The linearization produces a sequence of blocks. State is applied in this order.
3. Red blocks are ignored (their transactions are not applied).

This is why GHOSTDAG is a consensus for a linearizable state despite the DAG structure.

```rust
fn linearize_blue(blue_blocks: &[Block]) -> Vec<Block> {
    // Sort by blue point, then by hash for tie-breaking
    let mut sorted = blue_blocks.to_vec();
    sorted.sort_by(|a, b| {
        blue_point_order(a, b)
            .then_with(|| a.hash.cmp(&b.hash))
    });
    sorted
}
```

## Chain Selection in GHOSTDAG

When two DAGs compete (a fork in the DAG sense), GHOSTDAG selects the one with the higher blue score. The blue score is the cumulative work of the blue blocks.

```rust
fn select_canonical_dag(dag_a: &BlockDAG, dag_b: &BlockDAG) -> &BlockDAG {
    let score_a = blue_score(dag_a.blue_blocks());
    let score_b = blue_score(dag_b.blue_blocks());
    if score_a > score_b { dag_a } else { dag_b }
}
```

This is analogous to "heaviest chain" in PoW, but with blue score instead of cumulative difficulty of a linear chain.

## Validation in GHOSTDAG

A block is valid if:
1. It satisfies the PoW requirement (hash < target).
2. Its references are to valid blocks already in the DAG (or are the genesis).
3. It doesn't create a cycle (DAG property — but the references should naturally avoid cycles if they point to earlier blocks).
4. Its transactions are valid (signatures, no double-spend against the blue set UTXO state, etc.).
5. It follows the block format (correct number of references, timestamp rules, etc.).

**Important:** validity is checked against the current DAG, not just the previous block. The UTXO state is computed from the blue set linearization, so a block's transactions must be validated against that state.

## Implementation Considerations

### k Parameter

k is a protocol parameter (Kaspa uses k=16 or similar). It determines the cluster size. Smaller k → more aggressive colouring (more blocks red). Larger k → more blocks blue (slower finality? more work to overtake?). The value of k affects security and throughput. Choose k carefully and test.

### Performance

The colouring algorithm processes all blocks in the DAG. For large DAGs, this can be expensive. Kaspa optimizes by:
- Maintaining the blue set incrementally (not recomputing from scratch).
- Limiting the k-cluster computation to recent blocks.
- Using data structures for efficient cluster queries.

Do NOT recompute colouring from scratch on every new block in production. Incremental updates are essential.

### Spec Reference

This skill is a conceptual overview. The actual GHOSTDAG algorithm is defined in the Kaspa specification and research papers. Before implementing, read:
- The Kaspa GHOSTDAG paper/specification.
- The Kaspa node implementation (if available) for reference.
- Test against known DAGs with known colouring outcomes.

## Verification Checklist

- [ ] Understands that GHOSTDAG is for BlockDAG (multiple parent references), not a chain
- [ ] Understands the concept of k-cluster and blue/red colouring
- [ ] Understands that blue score (cumulative work of blue blocks) is the chain weight
- [ ] Understands that red blocks are excluded from the canonical state
- [ ] Understands that linearization orders the blue blocks for state application
- [ ] Understands that colouring must be deterministic and incremental (not recomputed from scratch)
- [ ] Understands the role of the mergeset in colouring
- [ ] Knows that the actual algorithm must be referenced from the Kaspa spec — this skill is conceptual

## Common Pitfalls

1. **Implementing the colouring algorithm from a simplified description.** The actual GHOSTDAG algorithm is subtle. A simplified version may be incorrect under adversarial conditions. Reference the spec.

2. **Recomputing colouring from scratch on every block.** This doesn't scale. GHOSTDAG coloring must be incremental — new blocks only affect the colouring of their cluster.

3. **Using "number of blue blocks" as the blue score.** The blue score is the sum of work (difficulty), not the count. A block with high work counts more than several low-work blocks.

4. **Confusing blue set with chain.** The blue set is not a chain — it's a set of blocks. Linearization produces a chain from it. Don't assume the blue blocks form a chain by themselves.

5. **Not handling the DAG structure correctly.** BlockDAG references can be complex. Ensure that references are validated (no cycles, valid parent blocks, etc.).

6. **Choosing k without analysis.** k affects security. Too small, and the DAG loses work (blocks become red). Too large, and finality is slow. Test with adversarial simulations.

7. **Ignoring that forks in a DAG are different from chain forks.** In a chain, a fork is two blocks at the same height. In a DAG, a fork is two competing DAGs (different blue sets). The selection rule is blue score comparison.

8. **Validating a block only against the last block, not the DAG state.** In a BlockDAG, the UTXO state comes from the linearized blue set. A block's transactions must be validated against that state, not just the immediate parent.

9. **Assuming GHOSTDAG is functionally equivalent to heaviest-chain PoW.** It's similar in spirit (work-based selection) but different in mechanism (DAG, k-cluster, blue/red). The properties (finality, throughput, security) differ.
