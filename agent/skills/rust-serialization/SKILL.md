---
name: rust-serialization
description: Use when choosing and using serialization in Rust: serde + serde_json for JSON, bincode for binary, rkyv for zero-copy deserialization, postcard for embedded/CBOR, prost for protobuf, and serialization design for FFI and persistence.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, serialization, serde, serde_json, bincode, rkyv, postcard, prost, protobuf, CBOR, zero-copy]
    related_skills: [rust-basics, rust-crypto, rust-ffi-unsafe]
---

# Rust Serialization

## Overview

Serialization is the process of converting Rust data structures to bytes (for storage, transmission, or FFI) and back. Rust's serialization ecosystem is built around **serde** — a framework of traits (`Serialize`, `Deserialize`) and derive macros that let you plug in different formats. The format choice determines performance, size, interoperability, and human-readability.

This skill covers the major formats and when to use each, plus common pitfalls in serialization design.

## When to Use

- JSON for interoperable APIs, human-readable config, web APIs
- Binary formats for persistence, internal protocols, or performance-critical paths
- Zero-copy deserialization for large data that's memory-mapped or streamed
- Protobuf/CBOR for cross-language contracts
- Custom binary formats for consensus-critical data where layout must be exact
- Serialization for FFI boundaries (see rust-ffi-unsafe)

**Don't use for:** serialization that's part of a consensus protocol without carefully specifying endianness, padding, and field ordering — those need their own skill and testing.

## Serde: The Framework

```toml
[dependencies]
serde = { version = "1", features = ["derive"] }
```

Serde is the abstraction layer. You derive `Serialize` and `Deserialize` on your types, and each format crate provides the encoder/decoder.

```rust
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
struct User {
    id: u64,
    name: String,
    email: String,
    active: bool,
}

// Rename fields for JSON
#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct ApiRequest {
    user_id: u64,
    #[serde(default)]
    verbose: bool,
}

// Skip fields during serialization
#[derive(Serialize)]
struct Internal {
    pub_key: String,
    #[serde(skip)]
    secret: String,   // never serialized
}
```

**Key derives:**
- `Serialize` — convert to a format's representation
- `Deserialize` — reconstruct from a format's representation
- Both together — round-trip capable

**Serde attributes:**
- `rename` / `rename_all` — change field names in the output format
- `default` — use `Default::default()` when field is missing on deserialization
- `skip` / `skip_serializing` / `skip_deserializing` — exclude from one or both directions
- `flatten` — flatten inner struct's fields into parent
- `tag` / `content` — for internally-tagged, externally-tagged, or adjacently-tagged enums
- `untagged` — serialize enum variants without a tag (deserializer guesses from structure)
- `serialize_with` / `deserialize_with` — custom serializer/deserializer functions

## serde_json — JSON

```toml
[dependencies]
serde_json = "1"
```

JSON is the most common interoperable format. Human-readable, widely supported, but verbose and slow compared to binary formats.

```rust
use serde::{Serialize, Deserialize};
use serde_json;

#[derive(Serialize, Deserialize, Debug)]
struct Point {
    x: f64,
    y: f64,
}

// Serialize to JSON string
let point = Point { x: 1.0, y: 2.0 };
let json = serde_json::to_string(&point).unwrap();
assert_eq!(json, r#"{"x":1.0,"y":2.0}"#);

// Serialize to prettified JSON
let pretty = serde_json::to_string_pretty(&point).unwrap();

// Serialize to Value (dynamic JSON)
let value = serde_json::to_value(&point).unwrap();
// value is serde_json::Value — can manipulate dynamically

// Deserialize from JSON string
let point: Point = serde_json::from_str(r#"{"x":1.0,"y":2.0}"#).unwrap();

// Deserialize from JSON Value
let point: Point = serde_json::from_value(value).unwrap();

// Work with Value directly
let json_str = r#"{"users":[{"id":1,"name":"Alice"},{"id":2,"name":"Bob"}]}#" ;
let root: serde_json::Value = serde_json::from_str(json_str).unwrap();
let users = root["users"].as_array().unwrap();
for user in users {
    println!("{}", user["name"].as_str().unwrap());
}
```

**JSON error handling:**

```rust
match serde_json::from_str::<Point>(input) {
    Ok(p) => p,
    Err(e) => {
        eprintln!("JSON parse error: {}", e);
        // e is serde_json::Error — gives line/column in some cases
    }
}
```

## bincode — Binary, Rust-only

```toml
[dependencies]
bincode = "1"
```

bincode is a compact binary format. It's Rust-specific (no cross-language support), fast, and compact. Good for internal persistence and IPC.

```rust
use serde::{Serialize, Deserialize};
use bincode;

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Player {
    name: String,
    score: u64,
    position: (f32, f32),
}

let player = Player {
    name: "Alice".into(),
    score: 42,
    position: (10.0, 20.0),
};

// Serialize to bytes
let bytes = bincode::serialize(&player).unwrap();

// Deserialize from bytes
let decoded: Player = bincode::deserialize(&bytes).unwrap();
assert_eq!(decoded.name, "Alice");

// Configurable: limit depth, change endianness
let bytes = bincode::serialize_with_cfg(
    &player,
    bincode::config::standard()
).unwrap();

// With custom limits (for untrusted input)
use bincode::config::standard;

let result = bincode::deserialize_with_cfg(
    &bytes,
    standard().with_max_depth(100)
);
```

**bincode considerations:**
- Not version-stable across Rust compiler versions without care (the format is stable, but the implementation may evolve).
- Not suitable for cross-language use.
- Good for trusted data (same-process, persisted locally).

## rkyv — Zero-Copy Deserialization

```toml
[dependencies]
rkyv = "0.7"
```

rkyv is designed for zero-copy deserialization: serialize to bytes once, deserialize by just casting a pointer — no allocation, no copying. This is powerful for large data that's memory-mapped or streamed.

```rust
use rkyv::{Archive, Deserialize as RkyvDeserialize, Serialize as RkyvSerialize};

#[derive(Archive, RkyvSerialize, RkyvDeserialize, Debug, PartialEq)]
pub struct GameState {
    player_name: String,
    score: u64,
    inventory: Vec<String>,
}

let state = GameState {
    player_name: "Alice".into(),
    score: 1000,
    inventory: vec!["sword".into(), "shield".into()],
};

// Serialize — produces a byte buffer
let bytes = rkyv::ser::to_bytes::<GameState>(&state).unwrap();

// Deserialize — zero-copy, just a pointer dereference
let archived = rkyv::de::shared::from_bytes::<GameState>(&bytes).unwrap();
let state: GameState = archived.deserialize()?;

assert_eq!(state.player_name, "Alice");

// The archived version is accessible without deserializing to owned data
let archived_state = archived.as_ref();
println!("Score: {}", archived_state.score);
```

**When to use rkyv:**
- Large data that you want to memory-map and read without deserializing
- Performance-critical deserialization paths
- Persistence formats where you want to avoid allocation

**Tradeoffs:**
- More complex API than serde + bincode
- The serialized format is versioned but not designed for cross-language use
- Requires understanding of `Archive`, `#[derive(Archive)]`, and the rkyv type system

## postcard — CBOR for Embedded

```toml
[dependencies]
postcard = "0.8"
```

postcard is a CBOR-based serializer optimized for embedded (no_std) and compact output. It's serde-compatible.

```rust
use serde::{Serialize, Deserialize};
use postcard;

#[derive(Serialize, Deserialize, Debug)]
struct SensorRead {
    temperature: f32,
    humidity: u8,
    timestamp: u64,
}

let reading = SensorRead { temperature: 22.5, humidity: 65, timestamp: 1234567890 };
let bytes = postcard::to_allocvec(&reading).unwrap();

let decoded: SensorRead = postcard::from_bytes(&bytes).unwrap();
assert_eq!(decoded.temperature, 22.5);
```

**When to use postcard:**
- Embedded targets (no_std)
- CBOR-based protocols
- Compact binary format with serde ergonomics

## prost — Protocol Buffers

```toml
[dependencies]
prost = "0.12"
prost-build = "0.12"   # build dependency for .proto compilation
```

Protocol Buffers are the cross-language standard for structured data. Define `.proto` files, compile to Rust structs with `prost-build`.

```proto
// user.proto
syntax = "proto3";

message User {
    uint64 id = 1;
    string name = 2;
    string email = 3;
    bool active = 4;
}
```

```rust
// build.rs
fn main() {
    prost_build::compile_protos(&["proto/user.proto"], &["proto/"]).unwrap();
}
```

```rust
// Generated by prost-build — use as normal Rust structs
use user::User;

let user = user::User {
    id: 1,
    name: "Alice".into(),
    email: "alice@example.com".into(),
    active: true,
};

let bytes = user.encode_to_vec().unwrap();
let decoded = user::User::decode(&bytes[..]).unwrap();
```

**pros and cons:**
- Cross-language, versioned, widely supported
- Requires `.proto` files and a build step
- More verbose than serde_json for simple cases

## Serialization Design Considerations

### Endianness

Binary formats must specify endianness. Rust's native endianness is the host's endianness. For cross-platform or network formats, specify little-endian or big-endian explicitly.

```rust
use serde::{Serialize, Deserialize};
use serde_bytes;

// For byte-order-sensitive binary formats, use crates that guarantee endianness:
// - bincode: uses little-endian by default (configurable)
// - postcard/CBOR: big-endian per CBOR spec
// - custom: use `byteorder` crate for explicit endianness
```

### Versioning and Schema Evolution

For formats that evolve over time (config files, network protocols, persisted data):

- Use optional fields with `#[serde(default)]` for forward compatibility (new fields that old clients don't send).
- Use `#[serde(rename = "old_name")]` for backward compatibility (renamed fields).
- Avoid removing fields — mark them `#[serde(skip_deserializing)]` or ignore them.
- For consensus-critical formats, version the format explicitly (e.g., a version field at the start).

### Human-Readable vs Binary

- JSON is human-readable and debuggable, but slow and large.
- Binary formats (bincode, postcard, rkyv, prost) are compact and fast, but not human-readable.
- For config files, prefer JSON or TOML (human-readable).
- For internal storage or wire protocol, prefer binary.

### Serialization of Enums

Serde handles enums in several ways:

```rust
// externally tagged (default) — {"Variant": { ... }}
#[derive(Serialize, Deserialize)]
enum Color {
    Red,
    Green { intensity: u8 },
    Blue(String),
}

// internally tagged — {"Color": "Red"} or {"Color": "Green", "intensity": 100}
#[derive(Serialize, Deserialize)]
#[serde(tag = "Color")]
enum Color {
    Red,
    Green { intensity: u8 },
    Blue(String),   // ERROR — Blue has data that can't be tagged this way
}

// adjacently tagged — {"Color": "Green", "fields": {"intensity": 100}}
#[derive(Serialize, Deserialize)]
#[serde(tag = "Color", content = "fields")]
enum Color {
    Red,
    Green { intensity: u8 },
    Blue(String),
}

// untagged — no tag, deserializer infers from structure
#[derive(Serialize, Deserialize)]
#[serde(untagged)]
enum Color {
    Red,                           // serializes to nothing (unit variant)
    Green { intensity: u8 },      // serializes to {"intensity": 100}
    Blue(String),                 // serializes to "blue string"
}
```

**Untagged enums are fragile** — deserialization can misidentify variants if the structures overlap. Use tagged enums for robust deserialization.

### Serialization for FFI

For FFI, binary data must match C layout exactly. Use `#[repr(C)]` structs and serialize field-by-field, or use a format like bincode that you convert to bytes and pass as a pointer + length.

```rust
// FFI-compatible struct
#[repr(C)]
#[derive(Serialize, Deserialize)]
struct FfiPoint {
    x: f64,
    y: f64,
}

// Serialize to bytes, pass to C as (ptr, len)
let point = FfiPoint { x: 1.0, y: 2.0 };
let bytes = bincode::serialize(&point).unwrap();
let ptr = bytes.as_ptr();
let len = bytes.len();
// pass ptr and len to C function
// C side must know the deserialization format or use Rust-side deserialization
```

For C ↔ Rust interoperability, often the best approach is:
- Use a simple, well-specified binary format
- Store the format spec in documentation
- Serialize on one side, deserialize on the other, both using the same Rust code

## Verification Checklist

- [ ] Can set up serde with derive and understand `Serialize`/`Deserialize` basics
- [ ] Can serialize/deserialize with `serde_json` (to_string, from_str, Value)
- [ ] Can serialize/deserialize with `bincode` for compact binary storage
- [ ] Can use `rkyv` for zero-copy deserialization and understand when it's worth the complexity
- [ ] Can use `postcard` for embedded/CBOR scenarios
- [ ] Can set up `prost` for protobuf cross-language serialization
- [ ] Understands serde attributes: `rename`, `default`, `skip`, `tag`/`content`/`untagged`
- [ ] Can choose between human-readable (JSON) and binary formats based on use case
- [ ] Understands versioning considerations: optional fields, renaming, avoiding removals
- [ ] Understands enum serialization strategies and when untagged is risky
- [ ] Knows that for FFI or consensus, binary layout (endianness, padding, field order) must be specified and tested

## Common Pitfalls

1. **Using `#[serde(untagged)]` on enums that have overlapping structures.** Deserialization can pick the wrong variant. Use tagged enums for robust deserialization.

2. **Forgetting `#[serde(default)]` on new fields.** When adding a new field to a serialized struct, old data won't have it. Without `default`, deserialization fails. Add `default` or make the field optional.

3. **Using `#[serde(skip)]` on a field that's required for correctness.** Skipped fields aren't serialized or deserialized — they'll be `Default::default()` or uninitialized. Ensure that's acceptable.

4. **Assuming bincode format is stable across all Rust versions.** The bincode format is stable, but if you're storing data long-term, test deserialization across compiler versions.

5. **Not bounding deserialization depth/size for untrusted input.** `bincode` and other deserializers can be driven to allocate large amounts of memory by crafted input. Use configurable limits.

6. **Using JSON for high-volume internal data.** JSON is slow and large compared to binary. Switch to bincode or another binary format for hot paths.

7. **Confusing `Serialize` and `Deserialize` bounds.** A type that only implements `Serialize` can be serialized but not deserialized. Both are needed for round-trip.

8. **Not testing round-trip serialization.** A type can serialize and deserialize successfully but lose information (e.g., floating-point precision, empty vs absent optional). Test with representative data.

9. **Relying on serde's default ordering for binary format.** Serde doesn't guarantee field order in the serialized output for all formats. For consensus-critical binary layout, use a format that specifies ordering explicitly or serialize manually.

10. **Using `serde_json::Value` as a substitute for proper deserialization.** `Value` is flexible but loses type safety. Prefer deserializing to a typed struct and handling errors properly.
