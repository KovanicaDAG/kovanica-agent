---
name: rust-crypto
description: Use when using cryptography in Rust: hashes (SHA-2, SHA-3, blake3, BLAKE2), MACs (HMAC, HKDF), symmetric encryption (AES-GCM, ChaCha20-Poly1305), asymmetric (ed25519, secp256k1, ECDH), random number generation, and constant-time operations for secret material.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, crypto, hashes, SHA-2, blake3, ed25519, secp256k1, AES-GCM, ChaCha20, HMAC, HKDF, rand, constant-time]
    related_skills: [rust-basics, rust-ffi-unsafe]
---

# Rust Crypto

## Overview

Rust's cryptography ecosystem favors well-audited crates with safe defaults: `ring` for core primitives, `ed25519-dalek` for Ed25519, `blake3` for the blake3 hash, `sha2`/`sha3` for SHA families, `aes-gcm` and `chacha20poly1305` for authenticated encryption, `rand` for randomness, `hkdf` for key derivation. Avoid implementing crypto primitives yourself — use audited crates.

**Golden rules:**
- Don't roll your own crypto.
- Don't use unauthenticated encryption (raw AES-CBC without HMAC).
- Don't reuse nonces/IVs with the same key.
- Use constant-time comparison for secrets (compares in fixed time regardless of where they differ).
- Seed RNG from OS entropy, not from time or predictable values.

This skill covers the common Rust crypto crates and patterns. For consensus-relevant crypto (block hashing, Merkle trees, signatures in a blockdag), see the blockchain crypto skills.

## When to Use

- Hashing data (file integrity, content addressing, proof-of-work inputs)
- Authenticated encryption (encrypt + verify integrity)
- Key derivation from a shared secret or password (HKDF, PBKDF2)
- Digital signatures (Ed25519 for signing, verify; ECDSA/secp256k1 for Bitcoin-style)
- Random number generation (keys, nonces, salts)
- HMAC for message authentication
- Diffie-Hellman key exchange (ECDH, X25519)
- Constant-time comparisons for token/signature verification

**Don't use for:** implementing a new hash function, designing a new cipher, or anything that requires a cryptography researcher. Use established primitives.

## Hashes

### SHA-2 (SHA-256, SHA-512)

```toml
[dependencies]
sha2 = "0.10"
```

```rust
use sha2::{Sha256, Digest};

let mut hasher = Sha256::new();
hasher.update(b"hello world");
let hash = hasher.finalize();   // generic Array<u8, 32>

let hash_bytes: [u8; 32] = hash.into();
println!("SHA-256: {:02x}", hex::encode(hash_bytes));

// one-shot convenience
let hash = sha2::Sha256::digest(b"hello world");
```

### SHA-3 (SHA3-256, SHA3-512, SHAKE)

```toml
[dependencies]
sha3 = "0.10"
```

```rust
use sha3::{Sha3_256, Digest};

let hash = Sha3_256::digest(b"data");

// XOF (extendable output function) — SHAKE128/256
use sha3::Shake256;
use sha3::digest::Output;

let mut hasher = Shake256::new();
hasher.update(b"input");
let output: Output<Shake256> = hasher.finalize();
// read arbitrary number of bytes from output
```

SHA-3 is a different construction from SHA-2 (Keccak). Not interchangeable for protocols that specify SHA-2.

### BLAKE2 / BLAKE3

```toml
[dependencies]
blake3 = "1"
# or blake2 = "0.10" for BLAKE2b/s
```

```rust
use blake3::Hasher;

let hash = Hasher::new().update(b"data").finalize();
let hash_bytes = hash.as_bytes();   // [u8; 32]

// keyed hashing (MAC) — BLAKE3 with a secret key
let hasher = Hasher::new_keyed(key);   // key: &[u8; 32]
let hash = hasher.update(b"data").finalize();
```

**Blake3** is fast, modern, and safe. Preferred over SHA-2 for new designs when compatibility isn't required. BLAKE2b is common in existing protocols (e.g., some PoW schemes).

## Authenticated Encryption

### AES-256-GCM

```toml
[dependencies]
aes-gcm = "0.10"
```

```rust
use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce
};

// Key: 32 bytes (256 bits)
let key = Aes256Gcm::generate_key(OsRng);
let cipher = Aes256Gcm::new(&key);

// Nonce: 12 bytes (96 bits), must be unique per key
let nonce = Aes256Gcm::generate_nonce(OsRng);

// Encrypt
let plaintext = b"secret message";
let ciphertext = cipher.encrypt(&nonce, plaintext.as_ref())
    .expect("encryption failed");

// Decrypt
let decrypted = cipher.decrypt(&nonce, ciphertext.as_ref())
    .expect("decryption failed");
assert_eq!(decrypted, plaintext);

// with associated data (not encrypted, but authenticated)
let nonce = Aes256Gcm::generate_nonce(OsRng);
let ciphertext = cipher.encrypt(
    &nonce,
    aead::Aad::from(b"additional data"),
    plaintext.as_ref()
).expect("encryption with AADATA failed");
```

**Critical:** Never reuse a nonce with the same key. If you need deterministic nonces (e.g., for a stream cipher pattern), derive them from a counter or key derivation, not from random (random can collide).

### ChaCha20-Poly1305

```toml
[dependencies]
chacha20poly1305 = "0.10"
```

```rust
use chacha20poly1305::{
    aead::{Aead, KeyInit, OsRng},
    ChaCha20Poly1305, Nonce,
};

let key = ChaCha20Poly1305::generate_key(OsRng);
let cipher = ChaCha20Poly1305::new(&key);
let nonce = ChaCha20Poly1305::generate_nonce(OsRng);

let ciphertext = cipher.encrypt(&nonce, b"secret").expect("encrypt failed");
let decrypted = cipher.decrypt(&nonce, &ciphertext).expect("decrypt failed");
```

ChaCha20-Poly1305 is a good choice when AES hardware acceleration isn't available (software-fast, constant-time by design).

### AES-CBC + HMAC (legacy, but required for some protocols)

For protocols that require CBC mode with HMAC (e.g., some existing systems), be careful:

```toml
[dependencies]
aes = "0.8"
cbc = "0.1"
hmac = "0.12"
sha2 = "0.10"
```

**Pattern:** encrypt-then-MAC. Encrypt first, then MAC the ciphertext (not the plaintext).

```rust
use aes::{Aes256, cipher::{Cipher, KeyInit, block_padding::Pkcs7]];
use cbc::{Decryptor, Encryptor};
use hmac::{Hmac, Mac};
use sha2::Sha256;

type HmacSha256 = hmac::Mac<Sha256>;

// Encrypt
let key = Aes256::generate_key(rand::thread_rng());
let iv = Aes256::generate_iv(rand::thread_rng());   // 16 bytes
let cipher = Aes256::new(&key);
let mut encryptor = cbc::Encryptor::<Aes256>::new_from_slices(&key, &iv).unwrap();
let ciphertext = encryptor.encrypt(b"plaintext", Pkcs7).unwrap();

// MAC the ciphertext
let mut mac = HmacSha256::new_from_slice(hmac_key).unwrap();
mac.update(&ciphertext);
let mac_value = mac.finalize().into_bytes();

// Decrypt (verify MAC first)
let mut mac = HmacSha256::new_from_slice(hmac_key).unwrap();
mac.update(&ciphertext);
mac.verify_slice(&mac_value).unwrap();   // panic on invalid MAC

let mut decryptor = cbc::Decryptor::<Aes256>::new_from_slices(&key, &iv).unwrap();
let plaintext = decryptor.decrypt(&ciphertext, Pkcs7).unwrap();
```

**Note:** This pattern is error-prone. Prefer AES-GCM or ChaCha20-Poly1305 for new designs.

## Asymmetric Cryptography

### Ed25519

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

// Generate a key pair
let signing_key = SigningKey::generate(&mut OsRng);
let verifying_key = signing_key.verifying_key();

// Sign
let message = b"hello world";
let signature: Signature = signing_key.sign(message);

// Verify
verifying_key.verify(message, &signature).expect("signature invalid");

// Serialize
let vk_bytes: [u8; 32] = verifying_key.to_bytes();
let sk_bytes: [u8; 32] = signing_key.to_bytes();
let sig_bytes: [u8; 64] = signature.to_bytes();

// Deserialize
let vk = VerifyingKey::from_bytes(&vk_bytes).unwrap();
let sk = SigningKey::from_bytes(&sk_bytes).unwrap();
let sig = Signature::from_bytes(&sig_bytes).unwrap();
```

Ed25519 is the modern choice for digital signatures. 32-byte keys, 64-byte signatures, fast, no nonce reuse issues (deterministic nonce derived from message + key).

### ECDSA with secp256k1 (Bitcoin-style)

```toml
[dependencies]
secp256k1 = "0.27"
```

```rust
use secp256k1::{
    ecdsa::{SigningKey, Verifier, Signature, RecoverableSignature},
    Secp256k1, rand::WinRRng,
};

let secp = Secp256k1::new();

// Signing key from secret bytes (32 bytes)
let secret = [0u8; 32];  // in real code, use a real secret
let signing_key = secp256k1::SecretKey::from_slice(&secret).unwrap();
let verifying_key = secp256k1::PublicKey::from_secret_key(&secp, &signing_key);

// Sign
let message_hash = secp256k1::Message::from_slice(&sha256_hash);
let signature = secp.sign_ecdsa(&message_hash, &signing_key);

// Verify
secp.verify_ecdsa(&message_hash, &signature, &verifying_key).unwrap();

// Recoverable signatures (Bitcoin transaction signing)
let recoverable_sig = secp.sign_ecdsa_recoverable(&message_hash, &signing_key);
let (recovered_sig, recovered_id) = recoverable_sig.recover(&message_hash, &verifying_key);
```

### ECDH (X25519)

```toml
[dependencies]
x25519-dalek = "2"
```

```rust
use x25519_dalek::{StaticDiffieHellman, EphemeralSecretKey, PublicKey, SharedSecret};

let my_secret = EphemeralSecretKey::random(&mut OsRng);
let my_public = my_secret.public_key();

// Remote's public key (received over the network)
let their_public: PublicKey = /* ... */;

let shared_secret = my_secret.diffie_hellman(&their_public);

// Derive a symmetric key from the shared secret
use hkdf::Hkdf;
use sha2::Sha256;

let hk = Hkdf::<Sha256>::new(None, &shared_secret.as_bytes());
let mut derived_key = [0u8; 32];
hk.expand(b"my context", &derived_key).unwrap();
```

## Key Derivation

### HKDF (HMAC-based Key Derivation)

```toml
[dependencies]
hkdf = "0.14"
sha2 = "0.10"
```

```rust
use hkdf::Hkdf;
use sha2::Sha256;

let salt = b"somesalt";   // optional, can be None
let ikm = b"input keying material";   // shared secret or other source

let hk = Hkdf::<Sha256>::new(Some(salt), ikm);

// Derive a 32-byte key
let mut key = [0u8; 32];
hk.expand(b"key context 1", &key).unwrap();

// Derive multiple keys with different info
let mut enc_key = [0u8; 32];
hk.expand(b"encryption key", &enc_key).unwrap();

let mut mac_key = [0u8; 32];
hk.expand(b"mac key", &mac_key).unwrap();
```

HKDF is the standard for deriving multiple keys from a single source. Use distinct `info` strings for each derived key.

### PBKDF2 (Password-Based KDF)

```toml
[dependencies]
pbkdf2 = "0.11"
sha2 = "0.10"
```

```rust
use pbkdf2::pbkdf2_hmac_array;
use sha2::Sha256;

let password = b"correct horse battery staple";
let salt = b"randomsalt";   // 16+ bytes recommended
let iterations = 100_000;   // higher = slower but more secure

let key = pbkdf2_hmac_array::<Sha256, 32>(password, salt, iterations);
```

**Warning:** PBKDF2 is intentionally slow. The iteration count should be tuned to your hardware and threat model. Use Argon2 (`argon2` crate) for newer password hashing — it's memory-hard and resists GPU attacks better.

### Argon2 (password hashing)

```toml
[dependencies]
argon2 = "0.5"
```

```rust
use argon2::{Argon2, Params, password_hash::SaltString};
use argon2::password_hash::rand_core::OsRng;

let salt = SaltString::generate(&mut OsRng);
let argon2 = Argon2::default();

let hash = argon2.hash_password(b"password", &salt)?;
// store hash.to_string() — includes algorithm, params, salt, hash

// Verify
let parsed = argon2::PasswordHash::new(&hash_str)?;
argon2.verify_password(b"password", &parsed)?;
```

## Random Number Generation

### OS Entropy (for keys, nonces, salts)

```toml
[dependencies]
rand = "0.8"
rand_core = "0.9"
```

```rust
use rand::prelude::*;
use rand::rand_core::OsRng;

// OS entropy, suitable for cryptographic use
let mut key = [0u8; 32];
OsRng.fill(&mut key);

// Or
let key: [u8; 32] = rand::random();

// Generate a nonce
let nonce: [u8; 12] = rand::random();

// Random usize, u64, etc.
let r: u64 = rand::random();
```

**Avoid:** `rand::thread_rng()` for cryptographic material — it's seeded from OS entropy but may use a CSPRNG design that's not constant-time. Prefer `OsRng` for secrets.

### Avoiding RNG Pitfalls

- Don't seed from time, PID, or other predictable values.
- Don't use `rand::distributions::Standard` for secrets — use `OsRng`.
- Don't reuse RNG state across security boundaries without reseeding.
- Don't assume `rand::random()` is cryptographically secure for all targets — check the backend.

## MAC (Message Authentication Codes)

### HMAC

```toml
[dependencies]
hmac = "0.12"
sha2 = "0.10"
```

```rust
use hmac::{Hmac, Mac};
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

let key = b"secret key";
let mut mac = HmacSha256::new_from_slice(key).expect("HMAC can take key of any size");
mac.update(b"message to authenticate");
let result = mac.finalize();
let code_bytes = result.into_bytes();   // [u8; 32]

// Verify
let mut mac = HmacSha256::new_from_slice(key).expect("HMAC can take key of any size");
mac.update(b"message to authenticate");
mac.verify(&code_bytes).expect("HMAC verification failed");
```

HMAC is used for message authentication when you share a symmetric key. Combine with encryption for authenticated encryption if not using AES-GCM/ChaCha20-Poly1305.

## Constant-Time Comparisons

For secrets (MACs, signatures, tokens), use constant-time comparison to prevent timing attacks:

```rust
use aes_gcm::aead::{Aead, KeyInit};
use generic_array::GenericArray;

// If you have two byte arrays and need to compare them in constant time:
use subtyping::constant_time_eq;   // or use `subtle` crate

use subtle::{ConstantTimeEq, Ct};

let ct1 = Ct::from_slice(&a);
let ct2 = Ct::from_slice(&b);
let is_equal = ct1.ct_eq(&ct2).into();

// subtle crate is the standard for constant-time operations in Rust
use subtle::ConstantTimeEq;

let a: [u8; 32] = ...;
let b: [u8; 32] = ...;
let equal = a.ct_eq(&b).into();   // true if equal, computed in constant time
```

**Why it matters:** If you compare a secret token with `==`, the comparison returns false as soon as a byte differs. An attacker can measure the response time and brute-force the secret one byte at a time. Constant-time comparison always takes the same time regardless of where the difference occurs.

## Crate Selection Guide

| Primitive | Recommended crate | Alternatives |
|---|---|---|
| SHA-256/512 | `sha2` | `ring` (via `ring::digest`) |
| SHA-3 | `sha3` | `ring` |
| BLAKE3 | `blake3` | — |
| BLAKE2b | `blake2` | — |
| AES-256-GCM | `aes-gcm` | `ring` |
| ChaCha20-Poly1305 | `chacha20poly1305` | — |
| Ed25519 | `ed25519-dalek` | `ring` (Ed25519 via `ring::signature`) |
| ECDSA secp256k1 | `secp256k1` | — |
| ECDH/X25519 | `x25519-dalek` | `ring` |
| HMAC | `hmac` + `sha2` | `ring` |
| HKDF | `hkdf` + `sha2` | `ring` |
| PBKDF2 | `pbkdf2` + `sha2` | `ring` |
| Argon2 | `argon2` | — |
| Random (OS) | `rand` + `rand_core` (OsRng) | `rand` alone |
| Constant-time | `subtle` | `crypto-common` |

## Security Verification Checklist

- [ ] Are you using authenticated encryption (AES-GCM, ChaCha20-Poly1305) instead of raw cipher modes?
- [ ] Is each nonce/IV unique per key (never reused)?
- [ ] Are keys generated with OS entropy (`OsRng`), not predictable values?
- [ ] Are secrets compared in constant time (`subtle::ConstantTimeEq`)?
- [ ] Is the KDF appropriate for the source material (HKDF for shared secrets, Argon2 for passwords)?
- [ ] Are you deriving separate keys for separate purposes (encryption, MAC) with distinct HKDF info strings?
- [ ] Is the crypto crate actively maintained and audited?
- [ ] Are private keys stored securely (not logged, not in plaintext config)?
- [ ] Is the algorithm choice justified, not just "whatever the first crate I found does"?
- [ ] Have you considered key rotation and revocation if this is a long-lived system?

## Common Pitfalls

1. **Using ECB mode.** AES-ECB reveals patterns in the plaintext. Never use it.

2. **Reusing a nonce with AES-GCM.** If you encrypt two messages with the same key + nonce, the security guarantees collapse (attacker can recover XOR of plaintexts). Generate a fresh random nonce for each encryption, or derive deterministically.

3. **Not authenticating associated data.** If you have data that isn't encrypted but must be integrity-protected (e.g., a header), pass it as AAD to AES-GCM/ChaCha20-Poly1305. Don't skip it.

4. **Comparing secrets with `==`.** Leads to timing attacks. Use `subtle::ConstantTimeEq`.

5. **Rolling HMAC-then-encrypt instead of encrypt-then-MAC.** Encrypt-then-MAC is the secure construction. HMAC-then-encrypt is vulnerable to certain attacks.

6. **Using SHA-1 or MD5 for new designs.** Collisions are practical. Use SHA-2, SHA-3, or BLAKE3.

7. **Deriving keys with simple hash instead of HKDF.** Hashing a shared secret directly gives you one key. HKDF gives you a structured, extensible derivation with provable properties.

8. **Using PBKDF2 with too few iterations.** PBKDF2's security comes from iteration count. 10,000 is too low for modern hardware; 100,000+ is more appropriate for passwords.

9. **Assuming `rand::thread_rng()` is a CSPRNG.** It uses a userspace CSPRNG seeded from OS entropy, but for secrets, prefer `OsRng` which directly uses the OS entropy source.

10. **Not handling decryption failures securely.** If decryption fails (wrong key, corrupted ciphertext), don't return an error that reveals whether the issue was the key or the ciphertext. Return a generic "decryption failed" error.
