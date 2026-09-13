---
name: rust-utxo-ledger
description: Use when implementing a UTXO-based ledger in Rust: UTXO model, transaction inputs/outputs, ownership via scripts or keys, double-spend prevention, UTXO set management, transaction validation, and block application.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [blockchain, UTXO, ledger, transactions, inputs, outputs, double-spend, ownership, validation, UTXO-set]
    related_skills: [blockchain-fundamentals, rust-consensus-pow, rust-crypto-primitives, rust-merkle-structures]
---

# Rust UTXO Ledger

## Overview

A UTXO (Unspent Transaction Output) ledger models value as a set of unspent outputs, each with an amount and a locking condition (who can spend it). A transaction consumes some UTXOs (inputs) and creates new UTXOs (outputs). The ledger state is the UTXO set. This is the Bitcoin model.

This skill covers the UTXO data model, transaction structure, validation rules, UTXO set management, and how blocks are applied to update the state.

## When to Use

- Implementing a UTXO-based blockchain
- Designing transaction structures with inputs and outputs
- Managing an in-memory or on-disk UTXO set
- Validating transactions (signatures, amounts, double-spends)
- Applying blocks to update the UTXO set
- Building a wallet that tracks UTXOs

**Don't use for:** account-model ledgers (use the account ledger skill), or smart contract state machines.

## UTXO Model

### UTXO Representation

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct Outpoint {
    tx_hash: Hash,   // hash of the transaction that created this output
    index: u32,      // output index within that transaction
}

#[derive(Debug, Clone)]
struct UTXO {
    outpoint: Outpoint,
    amount: u64,     // satoshis, atoms, etc.
    owner: Owner,    // locking condition: pubkey, script, etc.
}

#[derive(Debug, Clone)]
enum Owner {
    Pubkey(PublicKey),           // anyone with the private key can spend
    Script(Vec<u8>),             // more complex locking script
    MultiSig(Vec<PublicKey>, u32),  // m-of-n multisig (see RFC-001 in kovanica-protocol)
}
```

The UTXO set is a map from `Outpoint` to `UTXO`.

```rust
struct UTXOSet {
    utxos: HashMap<Outpoint, UTXO>,
}
```

### Transaction Structure

```rust
#[derive(Debug, Clone)]
struct Transaction {
    version: u32,
    inputs: Vec<TxInput>,
    outputs: Vec<TxOutput>,
    lock_time: u32,   // optional: block height or timestamp for lock
    // signature data may be in inputs or separate
}

#[derive(Debug, Clone)]
struct TxInput {
    outpoint: Outpoint,          // which UTXO this input spends
    unlocking_data: UnlockingData,  // signature/script to unlock the owner
}

#[derive(Debug, Clone)]
enum UnlockingData {
    Signature(Signature),            // signed by the owner of the UTXO
    Script(Vec<u8>),                 // script that satisfies the lock
    Multisig(Signature, Vec<Signature>),  // for multisig: one signature + others?
}

#[derive(Debug, Clone)]
struct TxOutput {
    amount: u64,
    owner: Owner,                    // who can spend this output
}
```

### Transaction Validity Rules

A transaction is valid if:
1. **All inputs exist in the UTXO set** — the referenced UTXOs are unspent.
2. **No double-spend** — no two inputs in the transaction (or across transactions in the same block) reference the same UTXO.
3. **Unlocking data satisfies the owner** — for a `Pubkey` owner, the signature must verify against the pubkey and the transaction (or a subset of it). For scripts, the script must evaluate to true.
4. **Amounts balance** — sum of inputs ≥ sum of outputs. The difference is the fee.
5. **No negative amounts, no overflow.**
6. **Outputs are well-formed** — valid owner, non-zero amount (unless allowed), etc.
7. **For coinbase/ genesis** — special rules (no inputs, or allowed to create new coins).

```rust
fn validate_transaction(tx: &Transaction, utxo_set: &UTXOSet, tx_index: usize) -> Result<(), ValidationError> {
    // 1. Check inputs reference existing UTXOs
    for input in &tx.inputs {
        if !utxo_set.contains(&input.outpoint) {
            return Err(ValidationError::MissingUTXO(input.outpoint));
        }
    }

    // 2. Check no double-spend within the transaction
    let outpoints: HashSet<_> = tx.inputs.iter().map(|i| i.outpoint.clone()).collect();
    if outpoints.len() != tx.inputs.len() {
        return Err(ValidationError::DoubleSpendWithinTx);
    }

    // 3. Check unlocking data for each input
    for (input, utxo) in tx.inputs.iter().zip(
        tx.inputs.iter().map(|i| utxo_set.get(&i.outpoint).unwrap())
    ) {
        if !verify_unlock(input, utxo) {
            return Err(ValidationError::InvalidUnlock);
        }
    }

    // 4. Check amounts balance
    let input_sum: u64 = tx.inputs.iter()
        .map(|i| utxo_set.get(&i.outpoint).unwrap().amount)
        .sum();
    let output_sum: u64 = tx.outputs.iter().map(|o| o.amount).sum();

    if output_sum > input_sum {
        return Err(ValidationError::OutputsExceedInputs);
    }

    // 5. Check outputs well-formed
    for output in &tx.outputs {
        if output.amount == 0 {
            return Err(ValidationError::ZeroOutput);   // or allow, depending on design
        }
    }

    Ok(())
}
```

### Signature Verification

For a `Pubkey` owner, the unlocking data is a signature. What is signed?

- In Bitcoin, the signature is over a "sighash" — a digest of the transaction with the input's script replaced by the output's ScriptPubKey, and other inputs excluded (or included in a specific way depending on sighash type).
- The signature must be valid for the corresponding pubkey.

```rust
fn verify_unlock(input: &TxInput, utxo: &UTXO) -> bool {
    match &utxo.owner {
        Owner::Pubkey(pubkey) => {
            match &input.unlocking_data {
                UnlockingData::Signature(sig) => {
                    // sign over the transaction (with sighash logic)
                    let msg = sighash_message(tx, input.index(), utxo);
                    pubkey.verify(&msg, sig)
                }
                _ => false,
            }
        }
        Owner::Script(script) => {
            // script evaluation — complex, depends on the script language
            evaluate_script(script, &input.unlocking_data)
        }
        Owner::MultiSig(pubkeys, m) => {
            // m valid signatures from the pubkeys
            match &input.unlocking_data {
                UnlockingData::Multisig(sig, other_sigs) => {
                    // verify sig is from one of the pubkeys, and other_sigs are from the rest
                    // ... count valid signatures, check >= m
                }
                _ => false,
            }
        }
    }
}
```

### Sighash (Transaction Digest for Signing)

The exact message that's signed matters. A common approach:

```rust
fn sighash(tx: &Transaction, input_index: usize, utxo: &UTXO) -> Hash {
    // Serialize a version of the transaction that includes:
    // - version
    // - inputs (with this input's script replaced by the UTXO's owner script)
    // - outputs
    // - lock_time
    // - (sighash type flag)
    // Then hash it
}
```

The sighash prevents a signature from being reused for a different transaction (e.g., spending the same input to a different output).

## UTXO Set Management

### Adding and Removing UTXOs

When a block is applied:
- For each transaction in the block:
  - Remove the inputs' UTXOs from the set.
  - Add the outputs as new UTXOs.

```rust
fn apply_transaction(tx: &Transaction, utxo_set: &mut UTXOSet) {
    // Remove inputs
    for input in &tx.inputs {
        utxo_set.utxos.remove(&input.outpoint);
    }

    // Add outputs
    let tx_hash = tx.hash();
    for (index, output) in tx.outputs.iter().enumerate() {
        let outpoint = Outpoint { tx_hash, index };
        utxo_set.utxos.insert(outpoint, UTXO {
            outpoint,
            amount: output.amount,
            owner: output.owner.clone(),
        });
    }
}
```

### UTXO Set Persistence

The UTXO set is large (Bitcoin's is hundreds of GB). Storage options:
- **In-memory** — only for testing or very small chains.
- **On-disk with a key-value store** — LevelDB, RocksDB.
- **Pruning** — remove spent UTXOs; keep only unspent.
- **UTXO snapshot** — a compact representation for quick startup.

For a new implementation, start with a `HashMap` in memory for testing, then move to a persistent store.

### UTXO Lookup by Owner

To find all UTXOs owned by a key (for wallet balance):

```rust
fn find_utxos_by_owner(utxo_set: &UTXOSet, owner: &Owner) -> Vec<UTXO> {
    utxo_set.utxos.values()
        .filter(|utxo| utxo.owner == *owner)
        .cloned()
        .collect()
}
```

This is O(n) over the UTXO set. For wallets, an index (Owner -> Vec<Outpoint>) speeds this up.

## Block Application

Applying a block to the UTXO set:

```rust
fn apply_block(block: &Block, utxo_set: &mut UTXOSet, state: &mut LedgerState) -> Result<(), Error> {
    // 1. Validate all transactions in the block
    for (i, tx) in block.transactions.iter().enumerate() {
        validate_transaction(tx, utxo_set, i)?;
    }

    // 2. Check no double-spend across transactions in the block
    let all_inputs: HashSet<_> = block.transactions.iter()
        .flat_map(|tx| tx.inputs.iter().map(|i| i.outpoint.clone()))
        .collect();
    if all_inputs.len() != block.transactions.iter()
        .flat_map(|tx| tx.inputs.iter())
        .count() {
        return Err(Error::DoubleSpendAcrossTx);
    }

    // 3. Apply transactions in order
    for tx in &block.transactions {
        apply_transaction(tx, utxo_set);
    }

    // 4. Update state (block height, hash, etc.)
    state.block_hash = block.hash();
    state.height += 1;

    Ok(())
}
```

## Genesis and Coinbase

### Genesis Block

The genesis block creates the initial UTXOs (the first coins). It has no inputs (or special coinbase inputs) and outputs that distribute the initial supply.

### Coinbase Transaction

In Bitcoin, the coinbase transaction is the first transaction in a block. It has no inputs (or a special input referencing the block height) and creates new coins (the block reward + fees).

```rust
fn is_coinbase(tx: &Transaction) -> bool {
    tx.inputs.is_empty()   // or has a coinbase input
}

fn validate_coinbase(tx: &Transaction, block_height: u64, subsidy: u64) -> Result<(), Error> {
    if !tx.inputs.is_empty() {
        return Err(Error::CoinbaseMustHaveNoInputs);
    }
    // Output sum should be subsidy + fees from other transactions
    let fee_sum: u64 = /* sum of fees from other txs in block */;
    let output_sum: u64 = tx.outputs.iter().map(|o| o.amount).sum();
    if output_sum != subsidy + fee_sum {
        return Err(Error::CoinbaseAmountMismatch);
    }
    Ok(())
}
```

## Verification Checklist

- [ ] Can represent an Outpoint (tx_hash + index) and a UTXO (outpoint, amount, owner)
- [ ] Can represent a transaction with inputs (outpoint + unlock) and outputs (amount + owner)
- [ ] Can validate a transaction: inputs exist, no double-spend, unlock valid, amounts balance
- [ ] Can verify a signature for a Pubkey owner (with sighash)
- [ ] Can apply a transaction to the UTXO set (remove inputs, add outputs)
- [ ] Can apply a block (validate all txs, check cross-tx double-spend, then apply)
- [ ] Can manage a UTXO set (add, remove, lookup by owner)
- [ ] Understands the coinbase/genesis special cases
- [ ] Understands that the UTXO set is the state — all validation is against it

## Common Pitfalls

1. **Not checking for double-spends across transactions in a block.** A block can have two transactions spending the same UTXO. Validate the entire block's inputs together, not per-transaction.

2. **Signing the wrong message for sighash.** If the sighash doesn't include the relevant parts of the transaction, a signature can be reused. Follow the reference design.

3. **Not validating that inputs exist in the UTXO set.** A transaction with a fake outpoint is invalid. Check the UTXO set.

4. **Allowing outputs with zero amount (if not intended).** Zero outputs can be used to bloat the UTXO set or as dust. Decide on a policy.

5. **Not tracking the transaction hash correctly.** An outpoint references the transaction by its hash. If the hash is computed differently than expected, the outpoint won't match.

6. **Assuming UTXOs are immutable.** UTXOs are removed when spent. The same outpoint can't be spent twice. The UTXO set is the source of truth.

7. **Not handling the coinbase transaction's special rules.** The coinbase has no inputs (or a special input) and creates new coins. It must be validated differently from regular transactions.

8. **Using a HashMap for the UTXO set without considering persistence.** A HashMap is fine for testing, but a real node needs a persistent, efficient UTXO store (LevelDB, RocksDB).

9. **Not indexing UTXOs by owner for wallet lookups.** Finding a wallet's balance by scanning the entire UTXO set is slow. Add an index.

10. **Confusing the UTXO set with the chain.** The UTXO set is the current state (unspent outputs). The chain is the history (all blocks). They're related but different.
