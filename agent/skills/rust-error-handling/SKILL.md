---
name: rust-error-handling
description: Use when designing error handling in Rust: thiserror for libraries, anyhow/eyre for applications, Result vs panic, error conversion with ?, backtraces, context, error chains, and when to return errors vs panic.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, errors, Result, thiserror, anyhow, eyre, panic, error-chain, backtraces]
    related_skills: [rust-basics, rust-advanced, rust-cli]
---

# Rust Error Handling

## Overview

Rust has two error handling strategies: **Result<T, E>** for recoverable errors (the function reports failure and the caller decides what to do) and **panic!** for unrecoverable errors (the thread panics, unwinding the stack or aborting). The ecosystem standardizes on `thiserror` for library error types and `anyhow`/`eyre` for application error handling.

The key design question: is this error something the caller can reasonably handle, or is it a bug? If the caller can handle it (e.g., file not found, network timeout, invalid input), use `Result`. If it's a logic error that indicates a bug (e.g., index out of bounds, invalid state invariant violated), use `panic!` or an assertion.

## When to Use

- Designing error types for a library
- Handling errors in an application's main function
- Propagating errors with `?`
- Adding context to errors for debugging
- Deciding whether to panic or return `Result`
- Building error chains with causes

**Don't use for:** exceptions, try/catch control flow (Rust doesn't have exceptions — panics are for unrecoverable, Result for recoverable).

## Result and `?`

### Basic Result Handling

```rust
use std::fs;

// Returns Result<String, std::io::Error>
fn read_file(path: &str) -> Result<String, std::io::Error> {
    fs::read_to_string(path)
}

// Handle explicitly
match read_file("config.toml") {
    Ok(contents) => println!("Read: {}", contents),
    Err(e) => eprintln!("Failed to read config: {}", e),
}

// Propagate with ?
fn read_config(path: &str) -> Result<String, std::io::Error> {
    let contents = fs::read_to_string(path)?;   // if Err, returns early with Err
    Ok(contents)
}
```

The `?` operator works on `Result<T, E>` and `Option<T>`. For `Result`, it converts `Err(E)` into an early return. For `Option`, it converts `None` into an early return with `None`.

**Requirement:** the function must return `Result<_, E>` (or `Option<_>`) where `E` is compatible with the error from `?`. `?` uses the `From` trait to convert error types:

```rust
fn read_config(path: &str) -> Result<String, MyError> {
    let contents = std::fs::read_to_string(path)?;   // converts io::Error -> MyError via From
    Ok(contents)
}

#[derive(Debug)]
struct MyError {
    message: String,
}

impl From<std::io::Error> for MyError {
    fn from(e: std::io::Error) -> Self {
        MyError { message: e.to_string() }
    }
}
```

### `?` on Option

```rust
fn find_user(id: u64) -> Option<User> {
    // ...
}

fn get_user_name(id: u64) -> Option<String> {
    let user = find_user(id)?;   // if None, returns None
    Some(user.name)
}
```

## Panic vs Result

### When to Panic

Panic when the error indicates a bug — a violated invariant, an impossible condition, or a caller contract that was broken:

```rust
fn get_item(index: usize, v: &[i32]) -> i32 {
    // Panics if index out of bounds — caller violated the contract
    v[index]
}

fn process_config(cfg: &Config) {
    // Panics if config is missing a required field — the config is invalid
    assert!(cfg.api_key.starts_with("sk-"), "API key must start with sk-");
}
```

**Panic use cases:**
- Function precondition violated (contract broken by caller)
- Internal invariant impossible to reach in correct code
- Unrecoverable state in a thread that should die rather than continue in a corrupted state

### When NOT to Panic

Don't panic for errors that are part of normal operation:

```rust
// BAD — panics on file not found, which is a normal error
fn read_config() -> Config {
    let contents = std::fs::read_to_string("config.toml").unwrap();   // panics
    parse(&contents).unwrap()   // panics
}

// GOOD — returns Result
fn read_config() -> Result<Config, ConfigError> {
    let contents = std::fs::read_to_string("config.toml")?;
    let config = parse(&contents)?;
    Ok(config)
}
```

### `unwrap()` and `expect()`

`unwrap()` panics on `Err` or `None` with a default message. `expect()` panics with a custom message.

```rust
let x = Some(5);
x.unwrap();           // 5
x.expect("x should be Some");   // 5, custom message on panic

let r: Result<i32, _> = Ok(5);
r.unwrap();          // 5
r.expect("expected Ok");   // 5
```

**Use `unwrap()` / `expect()` in:**
- Tests (failures are expected to panic, and the message helps)
- Prototypes and examples
- Cases where the error is truly impossible (e.g., after you've verified the invariant)

**Avoid in:**
- Production library code (propagate the error instead)
- Application code where the error is recoverable

## thiserror — Library Error Types

```toml
[dependencies]
thiserror = "1"
```

`thiserror` is the standard for library error types. It derives `Error` and provides ergonomic `#[from]` for automatic conversion.

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum MyError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Parse error: {msg} at position {pos}")]
    Parse {
        pos: usize,
        msg: String,
    },

    #[error("Validation failed: {reason}")]
    Validation { reason: String },

    #[error("Network error: {0}")]
    Network(#[from] reqwest::Error),

    // Error with a source (for error chains)
    #[error("Config error")]
    Config {
        #[source]
        source: std::io::Error,
        path: String,
    },

    // Catch-all for unexpected errors
    #[error("Unexpected error: {0}")]
    Unexpected(String),
}
```

**Key attributes:**
- `#[error("...")]` — Display implementation, with format placeholders
- `#[from]` — auto-implements `From<SourceError>` for automatic `?` conversion
- `#[source]` — marks this field as the error's cause (for `Error::source()`)

**Why `thiserror` for libraries:**
- Error types are part of the public API — they need to be structured, typed, and stable.
- Users of the library may want to match on specific error variants.
- The error type should implement `std::error::Error`, `Display`, `Debug`.

## anyhow — Application Error Handling

```toml
[dependencies]
anyhow = "1"
```

`anyhow` is for applications — a flexible, context-rich error type that wraps any `Error + Send + Sync + 'static`. It's convenient for `main()` and application-level code that doesn't need typed error matching.

```rust
use anyhow::{Context, Result, bail, ensure, Error};

fn read_config(path: &str) -> Result<String> {
    let contents = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read config from {path}"))?;
    Ok(contents)
}

fn validate_age(age: i32) -> Result<()> {
    ensure!(age >= 0, "Age must be non-negative, got {age}");
    ensure!(age <= 150, "Age seems unrealistic: {age}");
    Ok(())
}

fn do_something() -> Result<()> {
    if some_condition_not_met() {
        bail!("Condition not met: {details}");
    }
    Ok(())
}

fn main() -> Result<()> {
    let config = read_config("config.toml")?;
    validate_age(30)?;
    do_something()?;
    Ok(())
}
```

**anyhow API:**
- `Result<T>` — shorthand for `Result<T, anyhow::Error>`
- `Context` trait — `.with_context(|| "message")` adds context to errors
- `bail!` — creates an error and returns early
- `ensure!` — condition check, bails with message if false
- `anyhow!` — creates an error from a string or format

**Anyhow for applications:**
- Applications don't need to match on specific error variants — they just need to know something went wrong and display a message.
- `anyhow` collects context as errors propagate, building a chain that's useful for debugging.

## eyre — Alternative to anyhow

```toml
[dependencies]
eyre = "1"
```

`eyre` is similar to `anyhow` but with a focus on rich error reports (backtraces, error chains with colored output). Use it if you want backtrace support in application errors.

```rust
use eyre::{Result, WrapErr, eyre};

fn read_config(path: &str) -> Result<String> {
    std::fs::read_to_string(path)
        .wrap_err(format!("Failed to read config from {path}"))?
}

fn main() -> Result<()> {
    let _ = read_config("config.toml")?;
    Ok(())
}
```

## snafu — Error Handling with Context

```toml
[dependencies]
snafu = "0.8"
```

`snafu` provides a different approach: context is part of the error type definition, and the `?` operator automatically captures context.

```rust
use snafu::Snafu;

#[derive(Debug, Snafu)]
enum Error {
    #[snafu(display("IO error on {path}: {source}"))]
    Io {
        path: String,
        #[snafu(source)]
        source: std::io::Error,
    },

    #[snafu(display("Parse error at {pos}: {msg}"))]
    Parse {
        pos: usize,
        msg: String,
    },
}

fn read_config(path: &str) -> Result<String, Error> {
    std::fs::read_to_string(path)
        .context(IoSnafu { path: path.to_string() })?
}
```

`snafu` is useful when you want structured error types with context that's automatically captured by `?`, but it's less common than `thiserror`/`anyhow`.

## miette — Rich Error Reports

```toml
[dependencies]
miette = "7"
```

`miette` provides rich error reports with source code snippets, backtraces, and diagnostic output. Integrate with `thiserror` or `anyhow` for display.

```rust
use miette::{Diagnostic, Result, wrap_err};
use thiserror::Error;

#[derive(Debug, Error, Diagnostic)]
pub enum MyError {
    #[error("IO error")]
    #[diagnostic(code(my_io_error))]
    Io(#[from] std::io::Error),

    #[error("Parse error at {pos}")]
    #[diagnostic(code(my_parse_error), help("Check the format of the input"))]
    Parse { pos: usize },
}

fn main() -> Result<()> {
    let _ = std::fs::read_to_string("nonexistent.toml")
        .wrap_err("Failed to read config")?;
    Ok(())
}
```

## Error Chain and Sources

Every error type implementing `std::error::Error` has a `source()` method that returns the underlying cause (if any). This builds an error chain:

```rust
use std::error::Error;
use std::io;

#[derive(Debug)]
struct AppError {
    message: String,
    source: Option<Box<dyn Error + Send + Sync>>,
}

impl std::error::Error for AppError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        self.source.as_ref().map(|e| e.as_ref())
    }
}

impl std::fmt::Display for AppError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)?;
        if let Some(source) = &self.source {
            write!(f, "\nCaused by: {}", source)?;
        }
        Ok(())
    }
}
```

`thiserror` handles this automatically with `#[source]`.

## Backtraces

Enable backtraces with the `RUST_BACKTRACE` env var:

```bash
RUST_BACKTRACE=1 cargo run     # prints backtrace on panic
RUST_BACKTRACE=full cargo run  # full backtrace with source locations
```

In code, capture a backtrace at error creation:

```rust
use std::backtrace::Backtrace;

#[derive(Debug)]
struct ErrorWithBacktrace {
    message: String,
    backtrace: Backtrace,
}

impl std::fmt::Display for ErrorWithBacktrace {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}\n{}", self.message, self.backtrace)
    }
}
```

Backtraces are captured at the point of creation — they show where the error was created, not necessarily where it was propagated. Useful for debugging, but don't rely on them for production error reporting (they can be verbose).

## Common Patterns

### Application Main with anyhow

```rust
use anyhow::Result;

fn main() -> Result<()> {
    let config = load_config()?;
    let state = initialize_state(&config)?;
    run(state)?;
    Ok(())
}
```

The `Result` return from main prints the error with context and exits with code 1.

### Library Error Enum with Context

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("Database error on {site}: {0}")]
    Database { site: String, #[source] source: sqlx::Error },

    #[error("Validation error: {msg}")]
    Validation { msg: String },
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        AppError::Database {
            site: "unknown".into(),
            source: e,
        }
    }
}
```

### Fallible Functions with Multiple Error Sources

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum Error {
    #[error("IO: {0}")]
    Io(#[from] std::io::Error),

    #[error("Parse: {0}")]
    Parse(#[from] serde_json::Error),

    #[error("HTTP: {0}")]
    Http(#[from] reqwest::Error),

    #[error("Custom: {msg}")]
    Custom { msg: String },
}
```

Each `?` automatically converts the source error via `From`.

## Verification Checklist

- [ ] Can write a function returning `Result<T, E>` and propagate with `?`
- [ ] Can implement `From<E>` for custom error type to enable `?` conversion
- [ ] Can use `thiserror` to define a typed error enum with `#[error]`, `#[from]`, `#[source]`
- [ ] Can use `anyhow` for application errors with `Context`, `bail!`, `ensure!`
- [ ] Can decide when to panic (invariant violation) vs return `Result` (recoverable error)
- [ ] Can use `unwrap()` / `expect()` appropriately (tests, prototypes, impossible cases)
- [ ] Can add context to errors with `.with_context()` or `.wrap_err()`
- [ ] Can read an error chain (cause chain from `source()`)
- [ ] Understands that `?` on `Option` propagates `None`
- [ ] Understands that panics in library code are a bug (library should propagate errors)
- [ ] Can enable backtraces with `RUST_BACKTRACE=1`

## Common Pitfalls

1. **Using `unwrap()` in library code.** Libraries should propagate errors. `unwrap()` panics — the caller can't handle it.

2. **Panicking on recoverable errors.** File not found, network timeout, invalid user input are recoverable. Return `Result`. Only panic on bugs.

3. **Not adding context to propagated errors.** An error "Connection refused" is less useful than "Connection refused when connecting to database at db.example.com:5432". Add context at each layer.

4. **Using `anyhow` in libraries.** Libraries should expose typed errors so callers can match on them. `anyhow::Error` is opaque — callers can't match on variants. Use `thiserror` for libraries.

5. **Forgetting `#[source]` in error types with inner errors.** Without it, the error's cause chain is broken. `thiserror` handles this with `#[source]`, but manual impls need it.

6. **Swallowing errors.** `let _ = do_something().unwrap();` silently ignores errors. If you genuinely don't care, document why and use `.ok()` or `let _ = ...` with a comment.

7. **Providing useless error messages.** "Error" or "Failed" without context. Include what failed, why, and what was being attempted.

8. **Not testing error paths.** Tests that only exercise the happy path miss error handling bugs. Test with invalid input, missing files, network failures (use mock servers).

9. **Exposing internal error details in user-facing messages.** Internal paths, SQL queries, or stack traces shouldn't be shown to end users. Log them, show a user-friendly message.

10. **Inconsistent error types across a crate.** Pick one error type strategy and stick with it. Mixing `thiserror` enums, `anyhow`, and manual error structs makes the API confusing.
