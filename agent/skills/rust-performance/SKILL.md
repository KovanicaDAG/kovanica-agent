---
name: rust-performance
description: Use when optimizing Rust performance: benchmarking with criterion, profiling with perf/flamegraph, cargo-flamegraph, SIMD, allocator selection, LTO, codegen-units, and identifying hot paths before optimizing.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, performance, benchmark, criterion, profiling, flamegraph, SIMD, LTO, allocator, optimization]
    related_skills: [rust-basics, rust-async]
---

# Rust Performance

## Overview

Rust is fast by default, but performance still requires measurement. The workflow is: profile to find hot paths, benchmark to quantify improvements, then optimize with evidence. Avoid premature optimization — Rust's zero-cost abstractions are good but not free, and human intuition about hot spots is often wrong.

This skill covers measurement tools (criterion, perf, flamegraph, cargo-flamegraph), compiler configuration (LTO, codegen-units, opt-level), and common optimization patterns (SIMD, allocator choice, avoiding allocations, cache-friendly data).

## When to Use

- Benchmarking a function or crate to get reliable timing
- Profiling a running application to find hot spots
- Generating flamegraphs to visualize where time is spent
- Configuring release builds for maximum performance
- Choosing an allocator for a specific workload
- Using SIMD for hot numeric kernels
- Optimizing allocation patterns (reuse buffers, avoid cloning in hot paths)

**Don't use for:** micro-benchmarking without profiling first (profile, then benchmark the hot spot), or optimizing before measuring (you'll likely optimize the wrong thing).

## Benchmarking with Criterion

```toml
[dev-dependencies]
criterion = "0.5"

[[bench]]
name = "my_bench"
harness = false
```

```rust
use criterion::{criterion_group, criterion_main, Criterion, BenchmarkId};

fn bench_hash(c: &mut Criterion) {
    let mut group = c.benchmark_group("hash");

    for size in [100, 1000, 10000].iter() {
        group.bench_with_input(
            BenchmarkId::new("sha256", size),
            size,
            |b, &size| {
                b.iter(|| {
                    let data: Vec<u8> = (0..size).map(|i| i as u8).collect();
                    let hash = sha2::Sha256::digest(&data);
                    black_box(hash);   // prevent optimizer from removing the work
                });
            },
        );
    }

    group.finish();
}

fn black_box<T>(v: T) -> T {
    // Use std::hint::black_box in Rust 1.79+
    // Below is a fallback for older versions
    v
}

criterion_group!(benches, bench_hash);
criterion_main!(benches);
```

Run with:

```bash
cargo bench
```

Criterion produces:
- Statistical comparison (t-test) between runs
- HTML reports in `target/criterion/`
- Throughput measurements (bytes/sec, iterations/sec)

**Good benchmarking practices:**
- Use `black_box` to prevent the optimizer from eliminating work.
- Benchmark with representative input sizes.
- Run multiple iterations (criterion handles this).
- Compare against a baseline (criterion compares to the previous run by default).

### Benchmarking with Realistic Inputs

```rust
use criterion::{criterion_group, criterion_main, Criterion};

fn bench_parse_realistic(c: &Criterion) {
    // Read a real input file
    let input = std::fs::read_to_string("tests/fixtures/real_input.json").unwrap();

    c.bench_function("parse_real_input", |b| {
        b.iter(|| {
            let _ = parse_json(black_box(&input));
        });
    });
}
```

## Profiling with perf and flamegraph

### Linux perf

```bash
# Install perf ( Linux: apt install linux-tools-generic, or distro equivalent)
# Record a CPU profile
perf record -g -- ./target/release/my_app

# View the profile
perf report

# Generate a flamegraph
perf script | inferno-collapse-perf | inferno-flamegraph > flamegraph.svg
```

For flamegraphs:

```bash
# Install flamegraph tools (uses inferno or flamegraph.pl)
cargo install flamegraph   # or use perf + inferno
```

### cargo-flamegraph

```bash
cargo install cargo-flamegraph

# Generate a flamegraph for a release binary
cargo flamegraph --bin my_app

# With specific args
cargo flamegraph --bin my_app -- --flag value

# For a running process
cargo flamegraph -p 1234
```

The flamegraph shows the call stack: the x-axis is time (wider = more time), the y-axis is the call stack. Hot paths are wide at the top.

### Interpreting Flamegraphs

- **Wide bars at the top** — functions that take a lot of time directly.
- **Wide bars lower in the stack** — callers that spend time in their callees.
- **Self time vs total time** — self time is the time spent in the function itself (not in callees). Total time includes callees.
- **Look for unexpected wide bars** — often reveals where optimization is needed.

### Sampling vs Instrumentation

- **Sampling (perf)** — periodically samples the stack. Low overhead, good for production-like workloads. May miss very short functions.
- **Instrumentation (dhat, tracy)** — instruments every function entry/exit. Higher overhead, more precise for allocation tracking and fine-grained timing.

## Release Profile Optimization

```toml
# Cargo.toml
[profile.release]
opt-level = 3          # default — maximum optimization
lto = "thin"           # thin LTO — good balance of speed and compile time
                       # lto = "fat" — more optimization, slower compile
codegen-units = 1      # fewer codegen units = better optimization, slower compile
panic = "abort"        # smaller binary (no unwinding tables)
strip = true           # strip symbols from binary (smaller, but no backtraces)
```

**Tradeoffs:**

| Setting | Effect | Cost |
|---|---|---|
| `opt-level = 3` | Maximum optimization | Compile time |
| `lto = "thin"` | Cross-crate optimization, moderate compile overhead | Compile time |
| `lto = "fat"` | Maximum cross-crate optimization | Compile time (significant) |
| `codegen-units = 1` | Better optimization across the whole crate | Compile time |
| `panic = "abort"` | Smaller binary, no unwinding | Can't catch panics across FFI boundaries (but does abort) |
| `strip = true` | Smaller binary | No backtrace symbols |

For most applications, `lto = "thin"` + `codegen-units = 1` is a good balance. For maximum performance, use `lto = "fat"`.

### Incremental Compilation

```toml
[profile.release]
incremental = false   # disable incremental for release (faster final binary, slower rebuild)
```

Incremental compilation helps development rebuild speed but can slightly hurt release performance. Disable for release.

## SIMD

Rust supports SIMD via:
- Auto-vectorization by the compiler (LLVM) — often the easiest win
- Explicit SIMD with `std::simd` (portable SIMD, currently unstable) or `packed_simd` / `std::arch` (platform-specific)

### Auto-vectorization

Make loops vectorizable:

```rust
// Good — compiler can vectorize
fn sum_squares(data: &[f32]) -> f32 {
    let mut sum = 0.0f32;
    for &x in data {
        sum += x * x;
    }
    sum
}

// Less vectorizable — data dependency
fn sum_squares_cumulative(data: &[f32]) -> Vec<f32> {
    let mut result = Vec::with_capacity(data.len());
    let mut sum = 0.0f32;
    for &x in data {
        sum += x * x;
        result.push(sum);   // dependency chain — harder to vectorize
    }
    result
}
```

**Help the compiler vectorize:**
- Use simple loops without data dependencies.
- Avoid branches in hot loops (or make them predictable).
- Use iterators — they often vectorize well.
- Check with `cargo asm` or examine LLVM IR.

### Explicit SIMD (platform-specific)

```rust
use std::arch::x86_64::*;

#[cfg(target_arch = "x86_64")]
fn sum_avx2(data: &[f32]) -> f32 {
    unsafe {
        let mut sum = _ mm256_setzero_ps();
        let chunks = data.chunks(8);
        for chunk in chunks {
            let v = _ mm256_loadu_ps(chunk.as_ptr());
            sum = _ mm256_add_ps(sum, v);
        }
        // Horizontal sum of the 8 lanes
        let tmp = _ mm256_hadd_ps(sum, sum);
        let tmp2 = _ mm256_hadd_ps(tmp, tmp);
        _ mm_cvtss_f32(tmp2) + _ mm_cvtss_f32(_ mm256_extractf128_ps(tmp2, 1))
    }
}
```

Explicit SIMD requires `unsafe`, careful alignment handling, and platform-specific code. Use `std::arch` for platform-specific and `std::simd` (unstable) for portable.

### Portable SIMD (unstable, nightly)

```rust
#![feature(portable_simd)]

use std::simd::{f32x8, Simd, SimdPartialOrd, SimdFloat};

fn sum_squares_simd(data: &[f32]) -> f32 {
    let chunks = data.chunks(8);
    let mut total = f32x8::splat(0.0);
    for chunk in chunks {
        let v = Simd::<f32, 8>::from_slice(chunk);
        total += v * v;
    }
    total.reduce_sum()
}
```

Requires `#![feature(portable_simd)]` and nightly Rust.

## Allocator Choice

The default allocator (system allocator) is fine for most workloads. For specific cases, a custom allocator can help:

- **High allocation rate, many small allocations** — consider `jemallocator` (jemalloc) or `mimalloc`.
- **Real-time / low-latency** — avoid jemalloc's background threads, consider `system` or a pool allocator.
- **Embedded / no_std** — use a fixed-size allocator or an arena.

```toml
[dependencies]
jemallocator = "0.5"
```

```rust
#[global_allocator]
static ALLOC: jemallocator::Jemalloc = jemallocator::Jemalloc;
```

**Measure before switching:** allocator choice has complex effects. Test with your workload.

## Avoiding Allocations in Hot Paths

```rust
// BAD — allocates every call
fn process_data(input: &[u8]) -> Vec<u8> {
    let mut output = Vec::new();
    for &byte in input {
        output.push(byte * 2);
    }
    output
}

// GOOD — caller provides buffer
fn process_data_buf(input: &[u8], output: &mut Vec<u8>) {
    output.clear();
    for &byte in input {
        output.push(byte * 2);
    }
}

// GOOD — reuse a static buffer (if size is bounded)
use std::cell::RefCell;

thread_local! {
    static BUFFER: RefCell<Vec<u8>> = RefCell::new(Vec::with_capacity(4096));
}

fn process_data_tls(input: &[u8]) -> &[u8] {
    BUFFER.with(|buf| {
        let mut buf = buf.borrow_mut();
        buf.clear();
        for &byte in input {
            buf.push(byte * 2);
        }
        buf.as_slice()
    })
}
```

**Patterns:**
- Pre-allocate with `Vec::with_capacity` when size is known.
- Reuse buffers across calls.
- Use `&mut [T]` instead of returning `Vec<T>` when the caller owns the buffer.
- Use `SmallVec` for small vectors that rarely grow (stack-allocated up to N elements).

```toml
[dependencies]
smallvec = "1"
```

```rust
use smallvec::SmallVec;

type SmallVec<[u8; 8]> = SmallVec<[u8; 8]>;

let v: SmallVec<[u8; 8]> = SmallVec::new();   // stack-allocated for up to 8 elements
v.push(1);
v.push(2);
// ...
```

## Cache-Friendly Data Structures

### Struct of Arrays vs Array of Structs

```rust
// Array of Structs (AoS) — each element is a struct
struct Particle {
    x: f32,
    y: f32,
    vx: f32,
    vy: f32,
}
let particles: Vec<Particle> = ...;

// When iterating over x only, AoS loads all fields — cache waste
for p in &particles {
    do_something(p.x);   // loads x, y, vx, vy into cache
}

// Struct of Arrays (SoA) — separate arrays per field
struct Particles {
    x: Vec<f32>,
    y: Vec<f32>,
    vx: Vec<f32>,
    vy: Vec<f32>,
}

// When iterating over x only, SoA loads only x — better cache utilization
for &x in &particles.x {
    do_something(x);
}
```

SoA is better when you access one field at a time across many elements. AoS is better when you access all fields of one element at a time.

### Contiguous Memory

- Use `Vec<T>` (contiguous) instead of `LinkedList<T>` (scattered) for iteration-heavy workloads.
- Use slab allocators or pools for frequently allocated objects to reduce fragmentation.
- Align data for SIMD: `#[repr(simd)]` or `#[repr(C, align(N))]`.

## Avoiding Cloning in Hot Paths

```rust
// BAD — clones a String every call
fn process_name(name: String) {
    let lowercased = name.to_lowercase();   // allocates
    // ...
}

// GOOD — borrow
fn process_name(name: &str) {
    let lowercased: String = name.to_lowercase();   // still allocates if you need owned
    // ...
}

// GOOD — if you just need to read
fn process_name(name: &str) {
    for ch in name.chars() {
        // ...
    }
}
```

Clone in hot paths is a common performance pitfall. Prefer borrowing, or reuse buffers.

## I/O and Async Performance

- Use `tokio::fs` for async file I/O — but note that file I/O on Linux is still blocking at the syscall level (tokio uses a thread pool for file I/O). For high-throughput file I/O, consider `async-io` or `memmap` (memory-mapped files).
- Use buffered I/O (`BufReader`, `BufWriter`) for small reads/writes.
- For network I/O, tokio's async I/O is efficient — use `TcpStream`, `TlsStream` (via `tokio-rustls` or `tokio-openssl`).

## Verification Checklist

- [ ] Can set up a criterion benchmark and run with `cargo bench`
- [ ] Can use `black_box` to prevent optimizer elimination in benchmarks
- [ ] Can install and use `cargo-flamegraph` to generate a flamegraph
- [ ] Can read a flamegraph to identify hot paths
- [ ] Can configure `[profile.release]` for LTO, codegen-units, panic = abort
- [ ] Can identify a hot loop and check if it's vectorized (or help it vectorize)
- [ ] Can write a simple explicit SIMD function for a known architecture (with unsafe)
- [ ] Understands when to switch allocators and how to set a global allocator
- [ ] Can reduce allocations in a hot path by reusing buffers
- [ ] Understands AoS vs SoA tradeoffs for cache performance
- [ ] Knows to profile before optimizing, and to measure after optimizing

## Common Pitfalls

1. **Optimizing without measuring.** Human intuition about hot spots is unreliable. Profile first.

2. **Micro-optimizing a non-hot path.** A 10% improvement on a function that's 0.1% of runtime is wasted effort. Focus on the hot spots.

3. **Not using `black_box` in benchmarks.** The optimizer can eliminate "dead" computations that look unused. `black_box` tells the compiler the value is used.

4. **Benchmarking with debug builds.** Debug builds have no optimization — they don't reflect real performance. Benchmark release builds.

5. **Assuming SIMD is always faster.** SIMD helps for certain patterns (vectorizable loops, numeric kernels). For branch-heavy or scalar code, it may not help.

6. **Switching allocators without testing.** Allocators have different performance characteristics. jemalloc helps for some workloads, hurts for others. Test with your workload.

7. **Ignoring cache effects.** Code that's fast in CPU cycles can be slow if it thrashes the cache. Consider data layout and access patterns.

8. **Not measuring the whole system.** Optimizing one function may shift the bottleneck elsewhere. Re-profile after optimizing.

9. **Over-optimizing for the micro-benchmark.** A micro-benchmark with a specific input may not reflect real usage. Benchmark with representative inputs.

10. **Forgetting that `Vec::push` may reallocate.** In hot paths, `Vec::with_capacity` when the size is known, or reuse a buffer, to avoid repeated reallocation.
