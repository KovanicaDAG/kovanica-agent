---
name: rust-testing
description: Use when writing tests in Rust: unit/integration tests, doctests, #[cfg(test)], test modules, proptest property-based testing, cargo-fuzz fuzzing, mockall mocking, and when to test what.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, testing, unit-tests, integration-tests, doctests, proptest, fuzzing, mockall]
    related_skills: [rust-basics, rust-advanced]
---

# Rust Testing

## Overview

Rust has testing built into the toolchain: `#[test]` functions compiled and run with `cargo test`, doctests extracted from doc comments, and integration tests in the `tests/` directory. The ecosystem adds property-based testing (proptest), fuzzing (cargo-fuzz / libFuzzer), and mocking (mockall).

The testing philosophy: test behavior, not implementation. Use unit tests for public API correctness, integration tests for cross-module contracts, and property tests for invariants that should hold across many inputs.

## When to Use

- Writing unit tests for a function/module
- Setting up integration tests in `tests/`
- Adding doctests to public APIs
- Testing edge cases with property-based testing (proptest)
- Fuzzing a parser, deserializer, or adversarial-input function
- Mocking external dependencies in unit tests (mockall)

**Don't use for:** manual QA, E2E browser tests, or system integration testing that needs Docker/compose — those are outside Rust's testing scope.

## Test Types

### Unit Tests

Unit tests live in the same source file, inside a `#[cfg(test)]` module:

```rust
// src/lib.rs or src/my_module.rs
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_positive_numbers() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn add_negative_numbers() {
        assert_eq!(add(-2, -3), -5);
    }

    #[test]
    fn add_zero() {
        assert_eq!(add(0, 0), 0);
    }

    #[test]
    #[should_panic(expected = "index out of bounds")]
    fn indexing_panics() {
        let v = vec![1];
        let _ = v[5];   // panics
    }
}
```

`#[cfg(test)]` ensures the module and its tests are only compiled during `cargo test`, not during normal builds.

### Integration Tests

Integration tests live in `tests/` directory at the crate root. Each file in `tests/` is a separate crate that depends on your library:

```
my_crate/
  Cargo.toml
  src/
    lib.rs
  tests/
    integration_test.rs       # tests/
```

```rust
// tests/integration_test.rs
use my_crate::add;

#[test]
fn test_add_from_integration() {
    assert_eq!(add(2, 3), 5);
}
```

**Key difference:** integration tests test your public API only. They cannot access private functions or internal state. This is intentional — it tests the contract you expose.

### Doc Tests

Doctests are examples in documentation comments, run as tests:

```rust
/// Adds two numbers.
///
/// # Examples
///
/// ```
/// let result = my_crate::add(2, 3);
/// assert_eq!(result, 5);
/// ```
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
```

Run with `cargo test --doc`. Doctests demonstrate API usage and verify the examples compile and pass. Use them for the "happy path" of public APIs.

Doctest special markers:
- `ignore` — don't run this example as a test (for long examples)
- `no_run` — compile but don't run (for examples that take long or need setup)
- `compile_fail` — expect compilation to fail (for demonstrating error messages)
- `edition2021` — specify edition for the example

```rust
/// ```
/// // ignore: requires network access
/// use my_crate::fetch;
/// ```
```

## Assertions

Standard assertions:

```rust
assert!(condition);
assert_eq!(a, b);           // a == b, with debug output on failure
assert_ne!(a, b);           // a != b
panic!("custom message");    // fail with message
```

With optional message:

```rust
assert_eq!(a, b, "a and b should be equal");
assert!(x > 0, "x must be positive, got {}", x);
```

For results:

```rust
assert!(result.is_ok());
assert!(result.is_err());
assert_eq!(result.unwrap(), expected);
```

`assert_eq!` uses `Debug` formatting for diff output — types that implement `Debug` give better failure messages.

## Test Organization

### Tests Module Pattern

```rust
// src/lib.rs
pub fn public_fn() { /* ... */ }

mod internal {
    pub fn internal_helper() { /* ... */ }
}

// Public tests (visible to integration tests via pub use)
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_public_fn() { /* ... */ }
}

// If internal helpers need testing, test through public API or make internal pub(crate)
```

### Tests Directory Layout

```
my_crate/
  Cargo.toml
  src/
    lib.rs
  tests/
    common/            # shared test utilities (as a module)
    integration_test.rs
    another_test.rs
```

In `tests/common.rs` or `tests/common/mod.rs`:

```rust
// tests/common/mod.rs
pub fn setup_test_data() -> Vec<i32> {
    vec![1, 2, 3, 4, 5]
}

pub fn assert_approx_eq(a: f64, b: f64, epsilon: f64) {
    assert!((a - b).abs() < epsilon, "Mismatch: {} vs {}", a, b);
}
```

```rust
// tests/integration_test.rs
use my_crate::add;
use my_crate::tests_common;   // if you `pub use` it from lib, or just a helper crate

#[test]
fn test_with_common_setup() {
    let data = tests_common::setup_test_data();
    // ...
}
```

For shared test utilities that are private to tests, use a module in `tests/`:

```rust
// tests/common/mod.rs
pub fn helper() { /* ... */ }

// tests/integration_test.rs
mod common;

#[test]
fn test() {
    common::helper();
}
```

## Proptest (Property-Based Testing)

Proptest generates random inputs and tests that a property holds for all of them, shrinking to a minimal failing case on failure.

```toml
# Cargo.toml
[dev-dependencies]
proptest = "1.5"
```

```rust
use proptest::prelude::*;

// Strategy for generating test inputs
proptest! {
    #[test]
    fn test_reverse_is_involutive(s in ".*") {
        // any string, when reversed twice, returns to original
        let rev_once = s.chars().rev().collect::<String>();
        let rev_twice = rev_once.chars().rev().collect::<String>();
        prop_assert_eq!(s, rev_twice);
    }

    #[test]
    fn test_sort_ids_permutation(input in prop::collection::vec(0i32..1000, 0..100)) {
        let mut sorted = input.clone();
        sorted.sort();
        // sorted is same elements, different order
        let mut check: Vec<i32> = input.clone();
        check.sort();
        prop_assert_eq!(sorted, check);
        // sorted is non-decreasing
        for window in sorted.windows(2) {
            prop_assert!(window[0] <= window[1]);
        }
    }

    #[test]
    fn test_add_commutative(a in 0i32..1000, b in 0i32..1000) {
        prop_assert_eq!(add(a, b), add(b, a));
    }
}
```

**Strategies:**
- `".*"` — any string
- `0i32..1000` — ranged integer
- `prop::collection::vec(element_strategy, size_range)` — vectors
- `prop::collection::hash_map(key_strategy, value_strategy, size_range)` — HashMap
- Custom strategies via `Strategy` trait

**Tips:**
- Start with the "happy path" and common edge cases as unit tests, then add property tests for invariants.
- For fuzzer-targeted code (parsers, decoders), proptest is a good first pass; cargo-fuzz is the deep dive.
- Shrinking finds minimal counterexamples — read the shrunk output to understand what breaks.

## Fuzzing (cargo-fuzz)

Uses LLVM's libFuzzer to generate inputs that maximize code coverage and find crashes.

```bash
cargo install cargo-fuzz
cargo fuzz init      # creates fuzz/ directory
cargo fuzz add my_target   # creates fuzz/target/my_target/
cargo fuzz run my_target   # runs the fuzzer
```

```rust
// fuzz/fuzz_targets/my_target.rs
#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Test with arbitrary data — minimize binary size of harness for speed
    let _ = std::str::from_utf8(data);
    // exercise the parser
    if let Ok(s) = std::str::from_utf8(data) {
        let _ = my_crate::parse(s);
    }
});
```

**Fuzzing strategies:**
- Fuzz parsers, deserializers, network packet handlers, file format readers
- Fuzz the "interesting" entry points — the boundary functions that take external data
- Limit fuzzing time per session (e.g., `cargo fuzz run my_target -- -max_total_time=3600`)
- Use seed corpus: put valid sample inputs in `fuzz/corpus/my_target/` to guide the fuzzer

## Mocking with Mockall

```toml
[dev-dependencies]
mockall = "0.12"
```

```rust
use mockall::automock;

// #[automock] generates a MockMyService that implements MyService
#[automock]
trait MyService {
    fn fetch(&self, url: &str) -> Result<String, Error>;
    fn save(&self, key: &str, value: &str) -> Result<(), Error>;
}

#[test]
fn test_with_mock() {
    let mut mock = MockMyService::new();

    // Set expectation: fetch will be called with "http://example.com"
    mock.expect_fetch()
        .with("http://example.com")
        .times(1)
        .returning(|_| Ok("response".to_string()));

    let result = mock.fetch("http://example.com").unwrap();
    assert_eq!(result, "response");

    // If expectation not met, test panics at drop (or earlier with .check_in_display())
}
```

For async traits, mockall generates `MockMyService` that implements the async trait with `Box<dyn Future>` returns:

```rust
#[automock]
trait AsyncService {
    async fn fetch(&self, url: &str) -> Result<String, Error>;
}

#[tokio::test]
async fn test_async_mock() {
    let mut mock = MockAsyncService::new();
    mock.expect_fetch()
        .with("http://example.com")
        .returning(|| Ok("async response".to_string()));

    let result = mock.fetch("http://example.com").await.unwrap();
    assert_eq!(result, "async response");
}
```

**When mocking is appropriate:**
- Unit testing a function that depends on an external service (HTTP API, database, file system)
- Isolating the unit from slow/flaky/expensive dependencies
- Verifying interaction patterns (how many times called, with what arguments)

**When mocking is overused:**
- When your code is only tested with mocks, you're testing the mocks, not the real behavior. Add integration tests against real dependencies too.

## Test Attributes

| Attribute | Effect |
|---|---|
| `#[test]` | Marks function as a test |
| `#[should_panic]` | Test expects to panic |
| `#[should_panic(expected = "message")]` | Panic must contain substring |
| `#[ignore]` | Test skipped by default; `cargo test --ignored` runs them |
| `#[cfg(test)]` | Module compiled only in test mode |
| `#[cfg(target_os = "linux")]` | Conditional compilation for platform-specific tests |

## Running Tests

```bash
cargo test                    # run all tests (unit + integration + doctest)
cargo test --lib              # unit tests only (lib target)
cargo test --bin mybin        # binary tests only
cargo test --test integration_test   # one integration test file
cargo test my_module::tests::test_name   # specific test
cargo test -- --nocapture     # show println! output during tests
cargo test -- --test-threads=1   # run tests single-threaded (for shared state debugging)
cargo test --doc              # doctests only
cargo test --ignored          # run ignored tests
cargo test -- --quiet         # less output
```

## Coverage

```bash
cargo install cargo-tarpaulin
cargo tarpaulin --out Xml   # coverage report in XML (for CI integration)
cargo tarpaulin --out Html   # HTML report
```

Tarpaulin runs tests with coverage instrumentation. Note: tarpaulin has limitations with certain Rust features (proc macros, some async patterns); it's best-effort.

## Common Patterns

### Test Fixture Setup

```rust
fn setup() -> TestState {
    TestState {
        db: MemDb::new(),
        config: Config::default(),
    }
}

#[test]
fn test_with_fixture() {
    let state = setup();
    // ... test using state
}
```

### Parameterized Tests (manual)

Rust doesn't have a built-in parameterized test framework. Options:

```rust
#[test]
fn test_parse_variants() {
    let cases = vec![
        ("1", Ok(1i32)),
        ("42", Ok(42)),
        ("-5", Ok(-5)),
        ("abc", Err("not a number")),
    ];
    for (input, expected) in cases {
        let result = parse(input);
        match (result, expected) {
            (Ok(a), Ok(b)) => assert_eq!(a, b),
            (Err(e), Err(msg)) => assert!(e.to_string().contains(msg)),
            _ => panic!("unexpected result for input {}", input),
        }
    }
}
```

Or use `[case]` crate for data-driven tests.

### Async Tests

```rust
#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn test_async_fn() {
        let result = async_fn().await;
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn test_deterministic() {
        // deterministic ordering
    }
}
```

## Verification Checklist

- [ ] Can write `#[test]` functions with `assert!`, `assert_eq!`, `assert_ne!`
- [ ] Can create a `#[cfg(test)] mod tests` with `use super::*`
- [ ] Can add doctests to public functions and run with `cargo test --doc`
- [ ] Can write an integration test in `tests/` that uses only the public API
- [ ] Can use `#[should_panic]` and `#[should_panic(expected = "...")]`
- [ ] Can write a proptest with strategies for strings, integers, collections
- [ ] Can read a proptest failure's shrunk output to find the minimal failing input
- [ ] Can set up a cargo-fuzz target and run it for a bounded time
- [ ] Can create a mock with `#[automock]` and set expectations
- [ ] Can run specific tests with `cargo test --test <name>` and filter by test name
- [ ] Can run tests with `--nocapture` to see debug output
- [ ] Understands the difference between unit tests (same module, can test private) and integration tests (tests/, public API only)

## Common Pitfalls

1. **Testing implementation instead of behavior.** Test what the function does (output, side effects), not how it does it (internal state, private functions). Implementation tests break on refactoring.

2. **Too many mocks.** If every test is mocked, the test suite doesn't catch integration bugs. Use mocks for isolation in unit tests, but have integration tests against real dependencies.

3. **Not testing error paths.** Happy-path tests miss the edge cases. Explicitly test failure conditions, invalid inputs, and boundary values.

4. **Relying on test execution order.** Tests should be independent. If test B only passes because test A ran first, fix the isolation.

5. **Ignoring `#[ignore]` tests.** If tests are marked `#[ignore]`, run them periodically with `cargo test --ignored`. Ignored tests rot.

6. **Not shrinking in proptest.** When proptest finds a failure, the shrunk case tells you the minimal input. Don't skip reading it.

7. **Fuzzing the wrong targets.** Fuzz the boundary functions that process external data. Fuzzing internal helpers gives diminishing returns.

8. **Not running tests in CI.** Tests only matter if they run automatically. Set up CI to run `cargo test` on every push/PR.

9. **Using `unwrap()` in tests.** Tests can panic on `unwrap` failure — that's fine — but `unwrap()` makes the failure message less useful. Use `assert!` with explicit messages where the failure mode matters.

10. **Not cleaning up shared state between tests.** If tests share a database or file, ensure each test leaves a clean state or runs in isolation.
