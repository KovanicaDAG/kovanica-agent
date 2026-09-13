---
name: rust-crypto-primitives
description: Use when implementing core cryptographic primitives for blockchain: hash functions for blocks/txs, Merkle trees for tx inclusion, digital signatures (Ed25519, ECDSA, Schnorr), key generation, address derivation, and constant-time ops.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, blockchain, crypto, hashes, ed25519, ECDSA, Schnorr, merkle, addresses, key-gen, constant-time]
    related_skills: [rust-crypto, rust-merkle-structures, rust-utxo-ledger, rust-consensus-pow]
---

# Rust Crypto Primitives for Blockchain

## Overview

Blockchain systems are built on a small set of cryptographic primitives, each with a specific role. The choice of primitives determines security properties, performance, and interoperability. This skill covers the standard blockchain crypto toolkit: hashing, signatures, address derivation, Merkle proofs, and the constant-time discipline required for secret material.

## When to Use

- Designing the hash function for blocks, transactions, and state
- Implementing address generation from public keys
- Verifying signatures on transactions and blocks
- Building Merkle trees for tx inclusion proofs or state proofs
- Deriving keys, nonces, or addresses from seed material
- Ensuring constant-time operations for secrets

**Don't use for:** protocol-level consensus (see rust-consensus-*), or ZK circuits (see rust-zk-proofs). This is the basic crypto toolkit, not consensus or ZK.

## Hash Functions in Blockchain

### Common Choices

| Hash | Use cases | Notes |
|---|---|---|
| **SHA-256** | Bitcoin block/tx hashes, Bitcoin addresses | Standard, widely supported |
| **SHA-256d** (double SHA-256) | Bitcoin PoW, txids | Prevents length-extension attacks in PoW context |
| **RIPEMD-160** | Bitcoin addresses (pubkey hash) | Short, collision-resistant enough for addresses |
| **Keccak-256** (SHA-3 family) | Ethereum block/tx hashes, addresses | Not identical to SHA-3 (NIST standardized SHA-3 with different padding) |
| **BLAKE2b / BLAKE3** | Modern chains, fast hashing | Faster than SHA-2, safe |
| **Poseidon** | ZK-friendly (ZK-SNARK circuits) | Algebraic, efficient in circuits — not for general hashing |

### SHA-256 in Rust

```toml
[dependencies]
sha2 = "0.10"
hex = "0.4"
```

```rust
use sha2::{Sha256, Digest};

pub fn hash(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    let result = hasher.finalize();
    let mut hash = [0u8; 32];
    hash.copy_from_slice(&result);
    hash
}

pub fn hash_two(data: &[u8]) -> [u8; 32] {
    // Bitcoin-style double SHA-256
    let first = hash(data);
    hash(&first)
}

// Hash a block header (example)
pub fn hash_block_header(prev_hash: &[u8; 32], merkle_root: &[u8; 32], timestamp: u64, nonce: u64) -> [u8; 32] {
    let mut data = Vec::new();
    data.extend_from_slice(prev_hash);
    data.extend_from_slice(merkle_root);
    data.extend_from_slice(&timestamp.to_le_bytes());
    data.extend_from_slice(&nonce.to_le_bytes());
    hash(&data)
}
```

**Important:** The serialization of data before hashing must be deterministic and specified. Byte order, field order, and padding all matter. Document the serialization format.

### Keccak-256 (Ethereum-style)

```toml
[dependencies]
sha3 = "0.10"
# or use keccak crate directly
```

```rust
use sha3::Keccak256;

pub fn keccak256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Keccak256::new();
    hasher.update(data);
    let result = hasher.finalize();
    let mut hash = [0u8; 32];
    hash.copy_from_slice(&result);
    hash
}
```

**Note:** Ethereum uses Keccak-256, not the NIST SHA-3 standard. The difference is in padding. If you need Ethereum compatibility, use Keccak-256 specifically.

### Hashing for Content Addressing

For content-addressed storage (IPFS-style, or transaction hashes as identifiers):

```rust
// Hash the canonical serialization of a transaction
pub fn tx_hash(tx: &Transaction) -> TxId {
    let serialized = canonical_serialize(tx);   // deterministic encoding
    hash(&serialized)
}
```

The hash is the txid. The canonical serialization format must be part of the protocol spec.

## Digital Signatures

### Ed25519 (modern, recommended)

```toml
[dependencies]
ed25519-dalek = "2"
rand = "0.8"
```

```rust
use ed25519_dalek::{
    Signer, Verifier, SigningKey, VerifyingKey, Signature,
};
use rand::rand_core::OsRng;

pub struct KeyPair {
    pub signing_key: SigningKey,
    pub verifying_key: VerifyingKey,
}

impl KeyPair {
    pub fn generate() -> Self {
        let signing_key = SigningKey::generate(&mut OsRng);
        let verifying_key = signing_key.verifying_key();
        KeyPair { signing_key, verifying_key }
    }

    pub fn from_seed(seed: &[u8; 32]) -> Self {
        let signing_key = SigningKey::from_bytes(seed);
        let verifying_key = signing_key.verifying_key();
        KeyPair { signing_key, verifying_key }
    }

    pub fn sign(&self, message: &[u8]) -> Signature {
        self.signing_key.sign(message)
    }

    pub fn verify(&self, message: &[u8], signature: &Signature) -> bool {
        self.verifying_key.verify(message, signature).is_ok()
    }
}

// Address derivation (Ed25519 public key hash)
use sha2::Sha256;

pub fn derive_address(verifying_key: &VerifyingKey) -> [u8; 20] {
    let pubkey_bytes = verifying_key.as_bytes();
    let mut hasher = Sha256::new();
    hasher.update(pubkey_bytes);
    let hash = hasher.finalize();
    // Take last 20 bytes (like Bitcoin addresses, or first 20 for others)
    let mut address = [0u8; 20];
    address.copy_from_slice(&hash[12..32]);
    address
}
```

### ECDSA with secp256k1 (Bitcoin-style)

```toml
[dependencies]
secp256k1 = "0.27"
```

```rust
use secp256k1::{
    ecdsa::{SigningKey, Verifier, Signature},
    Secp256k1, Message,
};

pub struct SecpKeyPair {
    secret_key: secp256k1::SecretKey,
    public_key: secp256k1::PublicKey,
}

impl SecpKeyPair {
    pub fn generate() -> Self {
        let secp = Secp256k1::new();
        let secret_key = secp256k1::SecretKey::random(&mut OsRng, &secp);
        let public_key = secp256k1::PublicKey::from_secret_key(&secp, &secret_key);
        SecpKeyPair { secret_key, public_key }
    }

    pub fn sign(&self, message_hash: &[u8; 32]) -> Signature {
        let secp = Secp256k1::new();
        let msg = Message::from_slice(message_hash).unwrap();
        secp.sign_ecdsa(&msg, &self.secret_key)
    }

    pub fn verify(&self, message_hash: &[u8; 32], signature: &Signature) -> bool {
        let secp = Secp256k1::new();
        let msg = Message::from_slice(message_hash).unwrap();
        secp.verify_ecdsa(&msg, signature, &self.public_key).is_ok()
    }
}
```

### Schnorr (Taproot / BIP-340)

For Bitcoin Taproot compatibility:

```toml
[dependencies]
secp256k1 = "0.27"
```

```rust
use secp256k1::{
    schnorr::{SigningKey, VerifyingKey, Signature, sign_recoverable, verify},
    Secp256k1,
};

pub fn schnorr_sign(message: &[u8; 32], secret_key: &secp256k1::SecretKey) -> Signature {
    let secp = Secp256k1::new();
    let msg = Message::from_slice(message).unwrap();
    sign_recoverable(&secp, &msg, secret_key).unwrap()
}

pub fn schnorr_verify(message: &[u8; 32], signature: &Signature, public_key: &VerifyingKey) -> bool {
    let secp = Secp256k1::new();
    let msg = Message::from_slice(message).unwrap();
    verify(&secp, &msg, signature, public_key).is_ok()
}
```

### Signature Verification in Transaction Processing

```rust
pub fn verify_transaction(tx: &Transaction, utxo_set: &UtxoSet) -> bool {
    for input in &tx.inputs {
        let utxo = utxo_set.get(&input.outpoint)?;
        let pubkey = &utxo.owner_pubkey;

        // Verify the signature against the pubkey and the tx data being signed
        let signing_data = build_signing_data(tx, input);   // chain-specific
        match utxo.sig_type {
            SigType::Ed25519 => {
                let signature = Signature::from_bytes(&input.signature).unwrap();
                ed25519_dalek::VerifyingKey::from_bytes(pubkey)
                    .unwrap()
                    .verify(&signing_data, &signature)
                    .is_ok()
            }
            SigType::Ecdsa => {
                // secp256k1 verification
                // ...
            }
        }
    }
    true
}
```

## Address Derivation

### Bitcoin-style (pubkey hash)

```rust
use ripemd160::Ripemd160;

pub fn bitcoin_address(pubkey: &[u8]) -> String {
    // SHA-256 of pubkey, then RIPEMD-160
    let mut sha = Sha256::new();
    sha.update(pubkey);
    let hash = sha.finalize();

    let mut rm = Ripemd160::new();
    rm.update(&hash);
    let hash160 = rm.finalize();

    // Add version byte (0x00 for mainnet P2PKH) and checksum
    let mut payload = Vec::new();
    payload.push(0x00);
    payload.extend_from_slice(&hash160);

    // Checksum: first 4 bytes of SHA-256(SHA-256(payload))
    let checksum = {
        let mut sha = Sha256::new();
        sha.update(&payload);
        let h1 = sha.finalize();
        let mut sha2 = Sha256::new();
        sha2.update(&h1);
        sha2.finalize()[..4].to_vec()
    };
    payload.extend_from_slice(&checksum);

    // Base58 encode
    base58::encode(&payload)
}
```

### Ethereum-style (EOA address)

```rust
pub fn ethereum_address(public_key: &[u8]) -> [u8; 20] {
    // Keccak-256 of the uncompressed public key (without the 0x04 prefix)
    let mut hasher = Keccak256::new();
    hasher.update(&public_key[1..]);  // skip the 0x04 prefix byte
    let hash = hasher.finalize();
    let mut address = [0u8; 20];
    address.copy_from_slice(&hash[12..32]);
    address
}
```

### Bech32 (SegWit / native addresses)

```toml
[dependencies]
bech32 = "0.11"
```

```rust
use bech32::{bech32_decode, bech32_encode, FromBase32, ToBase32};

pub fn bech32_address(hrp: &str, data: &[u8]) -> String {
    let base32: Vec<u5> = data.to_base32();
    bech32_encode(hrp, &base32).unwrap()
}

pub fn decode_bech32_address(addr: &str) -> Result<(String, Vec<u8>), Box<dyn Error>> {
    let (hrp, bech32_data) = bech32_decode(addr)?;
    let bytes = bech32_data.from_base32()?;
    Ok((hrp, bytes))
}
```

## Merkle Trees

Merkle trees provide compact inclusion proofs for a set of items (txs in a block, state entries).

### Bitcoin-style Merkle Tree (P2PKH)

```rust
use sha2::{Sha256, Digest};

pub fn merkle_root(leaves: &[Vec<u8>]) -> Vec<u8> {
    if leaves.is_empty() {
        return vec![0u8; 32];   // empty merkle root (Bitcoin convention)
    }

    let mut layer: Vec<Vec<u8>> = leaves.iter().map(|l| l.clone()).collect();

    while layer.len() > 1 {
        let mut next_layer = Vec::new();
        for i in (0..layer.len()).step_by(2) {
            if i + 1 < layer.len() {
                let mut hasher = Sha256::new();
                hasher.update(&layer[i]);
                hasher.update(&layer[i + 1]);
                let hash = hasher.finalize().to_vec();
                next_layer.push(hash);
            } else {
                // Odd node: duplicate
                next_layer.push(layer[i].clone());
            }
        }
        layer = next_layer;
    }

    layer[0].clone()
}
```

**Bitcoin double-SHA-256 in Merkle trees:** Bitcoin uses double SHA-256 for txids, and then single SHA-256 for the Merkle tree hashing of txids. The protocol specifies exactly this.

### Merkle Proof (Inclusion Proof)

```rust
#[derive(Debug, Clone)]
pub struct MerkleProof {
    pub leaf: Vec<u8>,
    pub leaf_index: usize,
    pub total_leaves: usize,
    pub hashes: Vec<Vec<u8>>,   // sibling hashes from leaf to root
}

pub fn verify_merkle_proof(proof: &MerkleProof, root: &[u8]) -> bool {
    let mut hash = proof.leaf.clone();

    for (i, sibling) in proof.hashes.iter().enumerate() {
        let position = (proof.leaf_index >> i) & 1;
        let mut hasher = Sha256::new();
        if position == 0 {
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
```

### Merkle Tree with Leaves as Hashes

For transaction Merkle trees, leaves are typically the txids (hash of the serialized transaction). The Merkle root goes into the block header.

```rust
pub fn block_merkle_root(txs: &[Transaction]) -> Vec<u8> {
    let txids: Vec<Vec<u8>> = txs.iter()
        .map(|tx| tx_hash(tx))
        .map(|id| id.to_vec())
        .collect();
    merkle_root(&txids)
}
```

## Key Generation and Management

### Seed Generation

```rust
use rand::rand_core::OsRng;
use rand::RngCore;

pub fn generate_seed() -> [u8; 32] {
    let mut seed = [0u8; 32];
    OsRng.fill_bytes(&mut seed);
    seed
}
```

### BIP-39 Mnemonic (for user-facing key backup)

```toml
[dependencies]
bip39 = "0.11"
```

```rust
use bip39::{Mnemonic, Language};

pub fn generate_mnemonic() -> String {
    let mnemonic = Mnemonic::new(&mut OsRng, Language::English, 12);   // 12 words (128 bits + checksum)
    mnemonic.phrase().to_string()
}

pub fn mnemonic_to_seed(phrase: &str, password: &str) -> Vec<u8> {
    Mnemonic::from_str(phrase).unwrap().to_seed(password)
}
```

### Hierarchical Deterministic (HD) Keys (BIP-32)

```toml
[dependencies]
bip32 = "0.2"
secp256k1 = "0.27"
```

```rust
use bip32::{KeyChain, ExtendedKey};
use secp256k1::Secp256k1;

pub fn derive_hd_key(seed: &[u8], path: &[u32]) -> ExtendedKey {
    let secp = Secp256k1::new();
    let chain = KeyChain::new_master(network, seed).unwrap();
    let mut key = chain;
    for &index in path {
        key = key.derive(index).unwrap();
    }
    key
}

// BIP-44 path: m/44'/0'/0'/0/0 (Bitcoin mainnet, account 0, external chain, index 0)
let path = [44, 0, 0, 0, 0];
let key = derive_hd_key(seed, &path);
```

## Constant-Time Operations

For secret material (private keys, signatures), use constant-time comparisons and arithmetic to prevent timing attacks.

```toml
[dependencies]
subtle = "2"
```

```rust
use subtle::{ConstantTimeEq, Ct};

// Compare two byte arrays in constant time
pub fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    a.ct_eq(b).into()
}

// Use in signature verification:
pub fn verify_signature_constant_time(key: &[u8], msg: &[u8], sig: &[u8]) -> bool {
    // Use ed25519-dalek or secp256k1 which are constant-time by default
    // The library handles constant-time comparison internally
    // Don't write your own comparison for secret material
}
```

**Key point:** The signature verification libraries (ed25519-dalek, secp256k1) are designed to be constant-time. Don't write your own comparison for secrets — use the library.

## Hashing Standards Checklist

- [ ] Is the hash function specified unambiguously (which hash, how to serialize input)?
- [ ] Are all hashing operations using the same serialization format (field order, endianness)?
- [ ] Is the hash used for block headers, txids, addresses, and Merkle roots each specified?
- [ ] Are signatures verified with the correct hash of the signing data (not the raw tx)?
- [ ] Is the address derivation specified (which hash, which bytes, any encoding)?
- [ ] Is constant-time comparison used for secret material?
- [ ] Are key generation seeds sourced from OS entropy, not predictable values?
- [ ] Is the Merkle tree construction specified (double SHA-256 vs single, odd-node duplication)?

## Common Pitfalls

1. **Hashing different things under the same name.** "Tx hash" might mean hash of the serialized tx, or hash of a subset of fields. Specify what's hashed.

2. **Inconsistent serialization.** Hashing the same data structure with different field orders or endianness produces different hashes. The serialization format is part of the protocol.

3. **Using SHA-3 when Keccak-256 is needed.** NIST SHA-3 and Keccak-256 differ in padding. For Ethereum compatibility, use Keccak-256.

4. **Not using double SHA-256 where specified.** Bitcoin uses double SHA-256 for PoW and txids. Single SHA-256 in those contexts breaks compatibility.

5. **Deriving addresses with the wrong hash or wrong bytes.** Bitcoin addresses use RIPEMD-160 of SHA-256 of the pubkey, not just SHA-256. Ethereum addresses use the last 20 bytes of Keccak-256 of the pubkey.

6. **Writing custom signature verification instead of using audited libraries.** Use ed25519-dalek, secp256k1, or similar. Don't implement signature verification from scratch.

7. **Not verifying the signature on the correct data.** Signatures are on a hash of the tx/block/ data, not the raw bytes. The signing data construction is chain-specific and must be specified.

8. **Using non-constant-time comparison for secrets.** Leads to timing attacks. Use `subtle` or let the library handle it.

9. **Assuming all Ed25519 implementations are interoperable.** Ed25519 has variants (e.g., batched verification, different hashing of messages). Specify the exact variant.

10. **Not specifying the Merkle tree construction.** Odd number of leaves — duplicate the last one? Or use a different construction? Specify.
