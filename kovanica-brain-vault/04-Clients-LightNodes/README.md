# 04-Clients-LightNodes — Light Clients, FFI & Mobile

**Purpose**: Light node clients, UniFFI bindings, mobile integration.

## Contents

| File | Description |
|------|-------------|
| [skills-rust-client-notes.md](skills-rust-client-notes.md) | Rust client patterns and notes |

## Light Node Architecture

### UniFFI Bindings (`crates/kovanica-ffi`)
- **Language targets**: Kotlin (Android), Swift (iOS), Python, etc.
- **Package**: `uniffi.kovanica` (Kotlin), `kovanica` (Swift)
- **Core type**: `LightNode` — SPV light client

### Key Methods

| Method | Purpose |
|--------|---------|
| `LightNode(config)` | Create light node with config |
| `setValidatorSeed(seed)` | Set validator identity |
| `enableHybrid(rateNum, rateDen, nominalWork, retarget)` | Enable hybrid PoW + VRF |
| `bondStake(seed, amount)` | Bond stake for block production |
| `produceEmptyBlock()` | Produce a block |
| `send(fromSeed, amount, toSeed)` | Transfer native KVNC |
| `send_asset(fromSeed, amount, toSeed, assetId)` | Transfer asset |
| `receiveBlocks(blob)` | Sync from peer blob |
| `exportBlocks()` | Export blocks for peer |
| `selectedTip()` | Get current tip |
| `export_light_sync()` / `receive_light_sync(blob)` | SPV light sync |
| `filter_matches(filter, address)` | Watch-only address queries |
| `prove_tx(blockId, txId)` / `verify_tx_proof(proof)` | Merkle inclusion proofs |

### SPV Mode (Watch-Only Wallets)
- **Light sync blobs**: `KVLS` v1 format (headers + Golomb-Rice filters)
- **Verified through**: `SpvClient`
- **Address filtering**: `filter_matches`, `synced_filter_matches`

### Mobile Builds
- **Android**: `./crates/kovanica-ffi/build-android.sh` → AAR with jniLibs
- **iOS/macOS**: `./crates/kovanica-ffi/build-apple.sh` → xcframework
- **Dependencies**: `net.java.dev.jna:jna:5.14.0@aar` (Android)

## Configuration

```kotlin
LightConfig(
    k = 3,
    subsidy = 1000,
    founderAmount = 1000,
    founderSeed = 1,
    finalityDepth = ULong.MAX_VALUE,
    payloadPruningDepth = ULong.MAX_VALUE,
)
```

### Implementation Skills (from /root/rust/skills/)

| File | Description |
|------|-------------|
| [skills/rust-async/SKILL.md](../05-Agentic-Operations/skills/rust-async/SKILL.md) | **Async Rust** — tokio, async-std, futures, async traits, spawn |
| [skills/rust-serialization/SKILL.md](../05-Agentic-Operations/skills/rust-serialization/SKILL.md) | **Serialization** — serde, serde_json, bincode, postcard, rkyv, prost |
| [skills/rust-crypto/SKILL.md](../05-Agentic-Operations/skills/rust-crypto/SKILL.md) | **Rust crypto** — ring, ed25519-dalek, blake3, sha2, aes-gcm, rand, hkdf |

## Crate Reference

- `crates/kovanica-ffi` — UniFFI bindings, LightNode
- `crates/kovanica-dag` — Consensus (used by FFI)
- `crates/kovanica-state` — Ledger (used by FFI)