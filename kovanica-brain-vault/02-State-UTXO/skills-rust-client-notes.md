---
source: skills/rust-client-notes/SKILL.md
name: rust-client-notes
synced_at: 2026-09-12T08:33:08.796916+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rust-client-notes — synced from skills/rust-client-notes/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.796916+00:00

# Rust Client Notes for Kovanica

## Core dependencies

```toml
[dependencies]
ed25519-dalek = "2"
reqwest = { version = "0.12", features = ["json", "blocking"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
hex = "0.4"
# tokio = { version = "1", features = ["full"] }  # if you prefer async
```

## Signing pattern (mandatory)

1. Obtain sighash from `POST /api/prepare` (raw bytes or hex).
2. Sign with `ed25519_dalek::SigningKey`.
3. Encode the 64-byte signature as **128 lowercase hex** characters.
4. Include that hex in the body of `POST /api/submit`.

```rust
use ed25519_dalek::{SigningKey, Signer};
use hex;

// sighash: &[u8] from prepare response
let signature = signing_key.sign(sighash);
let sig_hex = hex::encode(signature.to_bytes()); // exactly 128 chars
```

## Key safety rules

- Never put the seed or `SigningKey` into any request body or log.
- Prefer deriving keys from the same path the official wallet uses (confirm against current wallet source).
- Keep signing fully client-side; the node only verifies 64-byte Ed25519 signatures.

## Minimal typed client skeleton

A robust client should:

1. Call `GET /api/head` on startup and cache `atom`, `min_fee` / `subsidy`, and (post-RFC-006) supply fields.
2. Expose a high-level `transfer(from, to, amount)` that internally does prepare → sign → submit and **never** accepts a private key in its public API surface (pass a signer trait/callback instead).
3. Filter UTXOs client-side for coinbase maturity (`created_at + 100 ≤ current_height`) even though the node already skips them.
4. Surface the two new ledger errors:
   - `SupplyCapExceeded`
   - `CoinbaseImmature`
5. After the RFC-006 reset, treat any previously cached addresses/balances as invalid.

## Fee estimation after activation

```rust
fn fee_floor_atoms_per_byte(subsidy: u64) -> u64 {
    std::cmp::max(1, subsidy / 500_000)
}
```

Prefer the live `subsidy` (or `min_fee`) from `/api/head` over any compile-time constant.

## Emission helper

For explorers or wallets that need "next-era subsidy" or remaining issuance, reuse the pure functions in `emission-math/SKILL.md`.

## Checklist when generating client code

- [ ] Live `/api/head` used for fee / subsidy
- [ ] Immature coinbases skipped
- [ ] 75/25 burn model understood (client only estimates; node enforces)
- [ ] New ledger errors handled
- [ ] No private keys in logs or HTTP bodies
- [ ] Works against both pre- and post-RFC-006 `/api/head` shapes (feature-detect the new fields)
