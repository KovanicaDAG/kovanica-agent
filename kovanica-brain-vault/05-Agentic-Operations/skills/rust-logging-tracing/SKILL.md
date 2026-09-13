---
name: rust-logging-tracing
description: Use when adding logging and observability to Rust: tracing spans and events, tracing-subscriber with env_logger, log macros, structured logging, field extraction, and when to use tracing vs log.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, logging, tracing, observability, spans, events, subscribers, structured-logging]
    related_skills: [rust-basics, rust-async, rust-cli, rust-error-handling]
---

# Rust Logging and Tracing

## Overview

Rust has two logging ecosystems:
- **`log`** — the traditional logging facade with macros `info!`, `warn!`, `error!`, `debug!`, `trace!`. Simple, widely used, but unstructured (strings with formatting).
- **`tracing`** — a modern observability framework with spans (structured context), events (structured logs), and subscribers (formatters, recorders). Spans nest and carry structured fields, enabling correlation across async tasks.

For new projects, **tracing** is the recommended choice: it provides structured data, async-aware spans, and integrates with the wider observability ecosystem (OpenTelemetry, metrics, profiling).

## When to Use

- Adding structured logging to an application
- Instrumenting async code with spans that track request lifecycles
- Building a service that needs request tracing, correlation IDs, and structured output
- Debugging with log levels and filtering
- Integrating with OpenTelemetry or a tracing-compatible backend

**Don't use for:** metrics (use `metrics` or `prometheus` crate), or profiling (use a profiler, not logging).

## The `log` Crate

```toml
[dependencies]
log = "0.4"
env_logger = "0.11"   # or log4rs, tracing-subscriber with log layer
```

### Basic Usage

```rust
use log::{info, warn, error, debug, trace, Level};

fn main() {
    env_logger::init();

    info!("Application starting");
    debug!("Debugging details: {:?}", some_data);
    trace!("Very verbose: {}", expensive_computation());

    if let Err(e) = run() {
        error!("Application failed: {}", e);
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    warn!("This is a warning");
    Ok(())
}
```

### Log Levels

| Level | When to use |
|---|---|
| `error` | Fatal errors, operation failed, system can't continue |
| `warn` | Something unexpected but non-fatal, degraded mode |
| `info` | Significant lifecycle events (started, stopped, connected) |
| `debug` | Details useful for debugging (request/response dumps, intermediate state) |
| `trace` | Very verbose, often disabled in production (per-step tracing) |

### Filtering

```bash
# Show everything at INFO and above
RUST_LOG=info cargo run

# Show a specific crate at DEBUG
RUST_LOG=my_crate=debug cargo run

# Show multiple crates
RUST_LOG=my_crate=debug,other_crate=info cargo run

# Show a module path
RUST_LOG=my_crate::database=debug cargo run
```

`env_logger` reads `RUST_LOG` env var at init time. Filter syntax: `crate[::path]=level`.

### Loggers

- `env_logger` — env var configuration, simple, good for development
- `log4rs` — Configurable via YAML/JSON file, similar to Java's log4j
- `tracing-subscriber` with a log layer — bridge `log` to `tracing`

## The `tracing` Ecosystem

```toml
[dependencies]
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
tracing-appender = "0.2"   # for file/logging appenders
```

### Core Concepts

- **Spans** — represent a duration of work, with structured fields (e.g., a request span with method, path, status).
- **Events** — represent a point in time (e.g., "request completed", "error occurred").
- **Subscribers** — receive spans and events, format them, and write them somewhere (console, file, network).

```rust
use tracing::{info, debug, error, span, Level, instrument};
use tracing_subscriber::fmt::SubscriberExt;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    // Create a span
    let request_span = span!(Level::INFO, "request", method = "GET", path = "/users");
    let _guard = request_span.enter();

    info!("Processing request");
    debug!("User ID: 42");

    // Span ends when _guard is dropped
}
```

### Span Attributes

```rust
use tracing::{span, Level, field};

// Spans with fields
let span = span!(
    Level::DEBUG,
    "database_query",
    db = "users",
    query = "SELECT * FROM users",
    duration_ms = 5
);

// Enter the span (activates it for the current thread/task)
let _guard = span.enter();

// Spans can be nested — entering a span inside another span nests them
{
    let inner = span!(Level::TRACE, "inner_work");
    let _inner_guard = inner.enter();
    // ...
}   // inner span ends
```

### `#[instrument]` Macro

Automatically creates a span for a function with its arguments as fields:

```rust
use tracing::instrument;

#[instrument]
async fn fetch_user(id: u64) -> Result<User, Error> {
    // span created automatically with fields: id
    // all `tracing::info!`, etc. inside are children of this span
}

#[instrument(skip(self))]
async fn handle_request(&self, req: Request) {
    // skip(self) — don't include self in the span fields
    // (useful to avoid large/verbose fields)
}

#[instrument(ret, err)]
fn divide(a: f64, b: f64) -> Result<f64, String> {
    // ret — include the return value in the span
    // err — include the error if it fails
}
```

**`#[instrument]` attributes:**
- `skip(self)` — skip `self` (use when self is large or verbose)
- `skip(field)` — skip a specific field
- `ret` — include the return value as a field
- `err` — include the error as a field (for `Result` returning functions)
- `fields(...)` — specify custom fields

### Events with Fields

```rust
use tracing::{event, Level, field};

event!(Level::INFO, user_id = 42, "User logged in");

// Structured event
event!(
    Level::DEBUG,
    db = "users",
    query = "SELECT * FROM users",
    duration_ms = 5,
    "Query completed"
);

// Event at current span's level
tracing::info!("Something happened");
```

### Async-Aware Spans

`tracing` is async-aware: spans survive across `.await` points. When a task is resumed after an `.await`, the span context is preserved. This is a key advantage over `log` for async code.

```rust
#[instrument]
async fn handle_request(req: Request) {
    let user = fetch_user(req.user_id).await;   // span survives the await
    process_user(user).await;                    // still in the same span
}
```

## Subscribers and Formatters

### Console Output (Default)

```rust
use tracing_subscriber::fmt;

tracing_subscriber::fmt::init();   // default: console, human-readable
```

### JSON Output

```rust
use tracing_subscriber::fmt::format::Json;

tracing_subscriber::fmt()
    .event_format(Json::default())
    .init();
```

For machine-readable output (log aggregation, ELK, etc.), JSON is the standard.

### Env Filter (RUST_LOG)

```rust
use tracing_subscriber::EnvFilter;

tracing_subscriber::fmt()
    .with_env_filter(EnvFilter::from_default_env())
    .init();
```

`EnvFilter::from_default_env()` reads `RUST_LOG` (same syntax as `env_logger`).

For programmatic filter configuration:

```rust
use tracing_subscriber::EnvFilter;

let filter = EnvFilter::new("info,my_crate::db=debug");
tracing_subscriber::fmt()
    .with_env_filter(filter)
    .init();
```

### File Appender

```rust
use tracing_subscriber::fmt::writer::FileWriter;
use tracing_appender::non_blocking;

let (non_blocking, _guard) = tracing_appender::non_blocking(std::fs::File::create("app.log")?);

tracing_subscriber::fmt()
    .with_writer(non_blocking)
    .init();

// _guard must be kept alive for the appender to flush — store it in state
```

`tracing_appender::non_blocking` provides a non-blocking writer suitable for high-throughput applications. The guard must be kept alive (e.g., in application state) to keep the background thread running.

### Multiple Subscribers

```rust
use tracing_subscriber::{Layer, layer::SubscriberExt};

let console = tracing_subscriber::fmt::layer();
let file = tracing_subscriber::fmt::layer()
    .with_writer(FileWriter::new("app.log"));
let filter = EnvFilter::from_default_env();

tracing_subscriber::registry()
    .with(filter)
    .with(console)
    .with(file)
    .init();
```

Use `registry()` to compose multiple layers.

## Structured Logging with Spans

### Correlation IDs

A common pattern: create a request/span at the entry point, extract it downstream, and use it for correlation.

```rust
use tracing::{info, span, Level};
use uuid::Uuid;

async fn handle_request(req: Request) -> Response {
    let request_id = Uuid::new_v4().to_string();

    let request_span = span!(
        Level::INFO,
        "request",
        request_id = request_id,
        method = req.method,
        path = req.path,
    );
    let _guard = request_span.enter();

    // All child spans and events inherit request_id
    let result = process_request(req).await;

    info!(status = result.status, "Request completed");
    result
}
```

### Database Queries as Spans

```rust
use tracing::{span, Level, instrument};

#[instrument(skip(pool))]
async fn query_users(pool: &PgPool, filter: Filter) -> Result<Vec<User>, Error> {
    let span = span!(
        Level::DEBUG,
        "db_query",
        table = "users",
        filter = format!("{:?}", filter),
    );
    let _guard = span.enter();

    let users = sqlx::query_as!(User, "SELECT * FROM users WHERE ...", ...)
        .fetch_all(pool)
        .await?;

    tracing::debug!(count = users.len(), "Query returned users");
    Ok(users)
}
```

### Error Events with Context

```rust
use tracing::{error, instrument};

#[instrument]
async fn do_work() -> Result<(), Error> {
    if let Err(e) = inner_work().await {
        error!(
            error = %e,
            error_type = "InnerWorkError",
            "Work failed"
        );
        return Err(e);
    }
    Ok(())
}
```

The `%` prefix on `error = %e` formats the error with `Display` in the event.

## Integration with OpenTelemetry

```toml
[dependencies]
tracing-opentelemetry = "0.23"
opentelemetry = "0.22"
opentelemetry_sdk = "0.22"
```

```rust
use tracing_subscriber::{Layer, layer::SubscriberExt};
use tracing_opentelemetry::OpenTelemetryLayer;

let otel_layer = OpenTelemetryLayer::new(
    opentelemetry_sdk::trace::TracerProvider::builder()
        .build_tracer("my-app")
        .into_inner()
);

tracing_subscriber::registry()
    .with(otel_layer)
    .init();
```

For full OpenTelemetry setup (exporters, resource, etc.), consult the `tracing-opentelemetry` docs.

## Metrics (Companion)

`tracing` is for logging/events, not metrics. For metrics:

```toml
[dependencies]
metrics = "0.23"
metrics-exporter-prometheus = "0.15"
```

```rust
use metrics::{describe_counter, describe_gauge, describe_histogram};

describe_counter!("requests_total", Unit::Count, "Total requests");
describe_gauge!("active_connections", Unit::Count, "Active connections");
describe_histogram!("request_duration", Unit::Seconds, "Request duration");

metrics::counter!("requests_total").increment(1);
metrics::gauge!("active_connections").set(42);
metrics::histogram!("request_duration").record(std::time::Duration::from_millis(50));
```

For Prometheus exposition:

```rust
use metrics_exporter_prometheus::PrometheusBuilder;

PrometheusBuilder::new().install().unwrap();
// exposes /metrics endpoint (via your web framework)
```

## Verification Checklist

- [ ] Can initialize `env_logger` and set `RUST_LOG` for filtering
- [ ] Can use `log` macros (`info!`, `warn!`, `error!`, `debug!`, `trace!`)
- [ ] Can create a `tracing` span and enter it
- [ ] Can use `#[instrument]` on a function and understand `skip`, `ret`, `err`
- [ ] Can emit events with structured fields
- [ ] Can set up `tracing-subscriber` with JSON output and env filter
- [ ] Can use `tracing_appender` for file logging
- [ ] Can compose multiple layers with `registry()`
- [ ] Understands that tracing spans survive across `.await` (async-aware)
- [ ] Can add correlation IDs to request spans
- [ ] Understands the difference between `log` (unstructured) and `tracing` (structured, spans)
- [ ] Knows to use a separate metrics crate for counters/gauges/histograms

## Common Pitfalls

1. **Logging inside a span without using the span's context.** If you manually create a span and log without entering it or using `#[instrument]`, the log event isn't attached to the span. Use `#[instrument]` or enter the span.

2. **Not filtering in production.** Without filters, tracing can produce large volumes of output. Use `EnvFilter` with appropriate defaults (e.g., `info` for production, `debug` for staging).

3. **Capturing large data in span fields.** Including a full request body or large struct in a span field makes the span verbose. Use `skip` or extract only the relevant fields.

4. **Using `log` in async code without understanding the limitation.** `log` macros don't carry span context — you lose the request/operation context across `.await`. `tracing` preserves it.

5. **Creating spans but not entering them.** A span that's created but never entered (no `_guard`) doesn't become the current span. Events inside it aren't children of it. Enter the span or use `#[instrument]`.

6. **Not keeping the tracing_appender guard alive.** The non-blocking appender uses a background thread that's stopped when the guard is dropped. Keep the guard in application state.

7. **Logging sensitive data.** Request headers, tokens, PII — be careful about what you log. Use redaction or skip sensitive fields.

8. **Using `println!` for logging in production.** `println!` goes to stdout, doesn't respect log levels, and isn't structured. Use `log` or `tracing`.

9. **Not testing log output.** Log levels and structured fields are part of the contract. Test that the right events are emitted at the right levels.

10. **Mixing `log` and `tracing` without a bridge.** If some dependencies use `log` and your code uses `tracing`, set up a `log` layer in `tracing-subscriber` to capture `log` events into the tracing system.
