---
name: rust-async
description: Use when writing async Rust: tokio runtime, async/await, Futures, spawn, channels, sync primitives, async traits, cancellation, error handling across tasks, and common async patterns and pitfalls.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [rust, async, tokio, futures, spawn, channels, async-traits]
    related_skills: [rust-advanced, rust-web, rust-ffi-unsafe]
---

# Rust Async

## Overview

Async Rust lets a single thread multiplex many concurrent operations via futures that run until they hit a waiting point (`.await`), then yield control back to the runtime. The dominant runtime is **tokio**; **async-std** is an alternative with a std-like API. This skill focuses on tokio, which has broader ecosystem support.

Async Rust's sharp edges: cancellation semantics, `'static` bounds on spawned tasks, Send/Sync requirements on futures, and the gap between "this compiles" and "this behaves correctly under cancellation/panic."

## When to Use

- Writing network services, HTTP servers, WebSocket handlers, gRPC servers
- Concurrent I/O: multiple HTTP requests, DB queries, file reads
- Background workers, timers, interval-based polling
- Any code that benefits from non-blocking I/O without threads-per-connection
- Spawning tasks, using channels, managing timeouts/cancellation

**Don't use for:** CPU-bound work (use rayon or threads — async doesn't parallelize CPU work), or blocking I/O in async context (use spawn_blocking).

## Runtime: Tokio

### Runtime flavours

```rust
// Multi-threaded (default, work-stealing)
#[tokio::main]
async fn main() { /* ... */ }

// Current-thread (single-threaded, for testing or lightweight embedding)
#[tokio::main(flavor = "current_thread")]
async fn main() { /* ... */ }

// Explicit runtime builder for fine control
let rt = tokio::runtime::Builder::new_multi_thread()
    .worker_threads(4)
    .enable_all()
    .build()
    .unwrap();
rt.block_on(async { /* ... */ });
```

`#[tokio::main]` is the standard entry point. Inside libraries, never assume a runtime is running — accept a `TokioHandle` or `Handle` or document that the caller must provide a runtime. Prefer `tokio::runtime::Handle::current()` to get a handle to the current runtime from within async code.

### Spawning Tasks

```rust
// Spawn an independent task, returns JoinHandle<T>
let handle = tokio::spawn(async {
    do_work().await?;
    "done"
});

// Wait for result (blocks current task)
let result = handle.await.unwrap();   // Result<T, JoinError>

// JoinError: task panicked or was cancelled
match handle.await {
    Ok(Ok(v)) => v,
    Ok(Err(e)) => eprintln!("task error: {e}"),
    Err(join_err) => {
        if join_err.is_panic() {
            eprintln!("task panicked");
        } else {
            eprintln!("task cancelled");
        }
    }
}
```

**Key point:** `tokio::spawn` requires the future to be `Send + 'static`. This means all data captured by the async block must be `Send` and owned (no borrowed references that don't live forever). This is the #1 compilation error when spawning.

```rust
// ERROR: closure may outlive borrowed value
let buf = String::from("hello");
tokio::spawn(async move {
    println!("{}", buf);   // OK — buf moved into task
    // println!("{}", &buf); // still OK — buf is owned by task
});

// ERROR if you try to capture a borrowed reference without 'static lifetime
let slice: &str = &some_owned_string;
tokio::spawn(async move {
    println!("{}", slice);   // ERROR — slice doesn't live long enough
});
```

Fix: own the data in the spawned task. `Clone` it, or `Arc` it if shared across tasks.

### Join and Select

```rust
// Join both futures concurrently
let (a, b) = tokio::join!(future_a, future_b);

// Race — whichever finishes first
let first = tokio::select! {
    a = future_a => a,
    b = future_b => b,
};

// Select with branches and priorities
tokio::select! {
    res = async_operation() => {
        println!("operation completed: {res:?}");
    }
    _ = tokio::time::sleep(Duration::from_secs(5)) => {
        println!("timeout");
    }
    _ = tokio::signal::ctrl_c() => {
        println!("shutdown signal");
    }
}
```

`tokio::select!` is not a fair scheduler — branches are polled in order. If one branch is always ready, it can starve others. Use `tokio::select!` with awareness, or use `FuturesUnordered` for a set of futures.

### Cancellation

When a task is dropped (including when `select!` branch is chosen and other branches are dropped), the future is cancelled. Cancellation runs `Drop` on all held resources, but **does not run code after the `.await` that was interrupted** — that code never executes.

```rust
async fn might_be_cancelled() {
    do_step_one().await;           // runs to completion or until cancellation
    // If cancelled here, do_step_two never runs
    do_step_two().await;
}
```

**Design rule:** treat cancellation as a valid and expected outcome. Resources should be cleaned up via `Drop`. Side effects that must happen (like "commit transaction" or "send acknowledge") should be in logic the caller explicitly triggers, not implied by "the future completed."

For cleanup on cancellation, use:
- `Drop` impls on wrapper types
- `scopeguard` / `defer!` patterns
- explicit cancellation tokens (see below)

### Cancellation Tokens

```rust
use tokio_util::sync::CancellationToken;

let token = CancellationToken::new();
let child = token.clone();

tokio::spawn(async move {
    // cooperative cancellation check
    token.cancelled().await;   // waits until cancelled
    println!("shutting down");
});

// cancel from the parent
token.cancel();
```

Cancellation tokens let you implement graceful shutdown: signal all tasks to stop, wait for them to finish current work, then exit.

## Futures

### The Future Trait

```rust
pub trait Future {
    type Output;
    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
}
```

You almost never implement `Future` manually. Use `async fn` / `async block` and the compiler generates the future for you. Manual implementation is needed only for custom wakers or low-level primitives.

### `async fn` in Traits

Stable since Rust 1.75 (with `#![feature(async_fn_in_trait)]` was required before). Before that, you needed the `async-traits` crate which returns `Box<dyn Future>`. Now:

```rust
trait HttpClient {
    async fn get(&self, url: &str) -> Result<String, Error>;
}

struct RealClient;

impl HttpClient for RealClient {
    async fn get(&self, url: &str) -> Result<String, Error> {
        /* ... */
    }
}
```

**Caveat:** async trait methods desugar to returning an anonymous associated type — this can interact poorly with `dyn Trait` (you get `dyn Future` objects). For trait objects, you still need `Box<dyn Future<Output = ...>>`. The `async-traits` crate remains useful for that case.

### `Send` and `Sync` on Futures

A future that is `Send` can be moved across threads. Tokio's multi-threaded scheduler requires spawned tasks to be `Send`. Most standard futures are `Send` if all their captures are `Send`. `Rc`, `Cell`, `RefCell` are not `Send` — if these appear in an async block, the spawn fails.

**Fix for non-Send types in async:**
- Replace `Rc` with `Arc` (both `Send` if inner is `Send`)
- Replace `Cell`/`RefCell` with `Mutex`/`RwLock` (tokio's or std's)
- Or, don't spawn that code — run it on the current thread

### Pin and Pinning

`Pin<&mut T>` is a pointer that guarantees `T` will not be moved after the pin is created. This is required for futures that have self-referential state (the compiler generated async state machines are self-referential). The compiler handles pinning for you when you use `.await`. You only need to worry about pinning when:
- Implementing a manual future/Stream
- Using `Box::pin` for heap-pinned data
- Working with intrusive collections

```rust
// Box-pin a future for dynamic dispatch or self-referential needs
let pinned: Pin<Box<dyn Future<Output = i32> + Send>> = Box::pin(async { 42 });
```

In practice: `.await` handles pinning. `tokio::spawn` requires `Send` but not manual pinning.

## Channels

### Tokio Channels

```rust
// Multi-producer, single-consumer (broadcast-style send)
let (tx, mut rx) = tokio::sync::mpsc::channel::<i32>(32);

// Send (backpressure — waits if full)
tx.send(42).await?;   // Err if receiver dropped

// Receive
while let Some(v) = rx.recv().await {
    println!("got {v}");
}

// Unbounded (no backpressure — warn if used)
let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<i32>();
tx.send(42);   // never blocks, can OOM

// Multi-producer, multi-consumer (broadcast — every receiver gets every message)
let (tx, mut rx1) = tokio::sync::broadcast::channel::<i32>(16);
let mut rx2 = tx.subscribe();
tx.send(42)?;
// both rx1 and rx2 receive 42

// Many producer, one consumer (watch — latest value only)
let (tx, rx) = tokio::sync::watch::channel(0i32);
tx.send(1)?;   // all current receivers get 1
tx.send(2)?;   // all current receivers get 2 (and drop 1)
```

**Channel selection guide:**
- **mpsc** — task-to-task communication, ordered, backpressure. Most common.
- **broadcast** —/pub-sub where every subscriber needs every message. Each subscriber gets its own subscription.
- **watch** — observe latest value (config, state snapshot). Receivers don't get history; they get the latest on subscribe and on each send.
- **oneshot** — single message from one sender to one receiver. Useful for request/response between tasks.

```rust
// oneshot — request/response between tasks
let (tx, mut rx) = tokio::sync::oneshot::channel();
tokio::spawn(async move {
    let result = do_work().await;
    tx.send(result).ok();   // ignore failure if receiver dropped
});
let result = rx.await?;
```

### `std::sync::mpsc` vs Tokio Channels

Use `std::sync::mpsc` only when communicating between sync threads. In async code, use tokio channels — they're async-aware and play well with `.await`.

### Deadlock Avoidance

Deadlocks in channels:
- Don't hold a lock while sending on a bounded channel that might fill up and block.
- Don't send on a channel while holding a mutex that the receiver needs.
- Use `try_send` for fire-and-forget where blocking is unacceptable.

## Sync Primitives in Async

Prefer async-aware synchronization when the critical section may `.await`:

| Use case | Tokio primitive | Standard equivalent |
|---|---|---|
| Exclusive access, may await | `tokio::sync::Mutex` | `std::sync::Mutex` |
| Read-heavy, may await | `tokio::sync::RwLock` | `std::sync::RwLock` |
| Wait for flag/condition | `tokio::sync::Notify` | `std::sync::Condvar` |
| Once-only initialization | `tokio::sync::OnceCell` (or `once_cell::sync::OnceCell`) | `std::lazy::LazyLock` (std since 1.80) |
| Many readers, single value | `tokio::sync::watch` | — |

**Rule:** if your critical section contains `.await`, use tokio's sync primitives. If it's pure computation with no `.await`, std primitives are fine and have less overhead.

```rust
// BAD — holding std Mutex across .await (not async-aware, blocks thread)
let lock = std::sync::Mutex::new(0);
let guard = lock.lock().unwrap();
do_async_thing().await;   // holds lock across await — bad
*guard += 1;

// GOOD — tokio Mutex, locks across .await are fine (they release while waiting)
let lock = tokio::sync::Mutex::new(0);
let mut guard = lock.lock().await;
do_async_thing().await;   // lock is still held but other tasks can proceed
*guard += 1;
// guard dropped here
```

**Note:** Even with tokio Mutex, holding a lock across `.await` means other tasks waiting on that lock are blocked until the holder resumes. Keep critical sections short.

## Async Error Handling

```rust
// propagate with ? inside async fn -> Result
async fn fetch(url: &str) -> Result<String, Error> {
    let resp = reqwest::get(url).await?;
    let text = resp.text().await?;
    Ok(text)
}

// join multiple futures, collect results
let results = tokio::join!(fetch("a"), fetch("b"));
// results is (Result<String, Error>, Result<String, Error>)

// handle each, don't fail all on first error
let (a, b) = results;
let a = a?;
let b = b?;
```

`tokio::join!` does NOT short-circuit — all futures run to completion. If you want early termination on error, use `try_join`:

```rust
// fails fast on first Err
let (a, b) = tokio::try_join!(fetch("a"), fetch("b"))?;
```

## Common Async Patterns

### Graceful Shutdown

```rust
use tokio::signal;
use tokio_util::sync::CancellationToken;

let shutdown_tx = CancellationToken::new();
let shutdown_rx = shutdown_tx.clone();

let server = tokio::spawn(async move {
    // server loop checks cancellation
    loop {
        tokio::select! {
            _ = shutdown_rx.cancelled() => {
                println!("shutdown signal received");
                break;
            }
            conn = accept_next_connection() => {
                handle_connection(conn).await;
            }
        }
    }
});

// wait for SIGINT/SIGTERM
signal::ctrl_c().await.ok();
println!("Got ctrl-c, initiating shutdown");

shutdown_tx.cancel();   // signal all tasks
server.await.ok();      // wait for server to finish
```

### Fan-out / Fan-in

```rust
// Fan-out: spawn N workers
let (tx, mut rx) = tokio::sync::mpsc::channel(32);
for worker_id in 0..4 {
    let tx = tx.clone();
    tokio::spawn(async move {
        while let Some(job) = rx.recv().await {
            process_job(worker_id, job).await;
        }
    });
}
drop(tx);   // close channel when all producers done

// Fan-in: collect results
let mut results = Vec::new();
for _ in 0..4 {
    results.push(tokio::spawn(async move {
        /* produce result */
    }));
}
let results: Vec<_> = futures_util::future::join_all(results).await;
```

### Rate Limiting

Use a semaphore for concurrency limiting:

```rust
let semaphore = std::sync::Arc::new(tokio::sync::Semaphore::new(10));  // 10 concurrent
let mut handles = vec![];

for i in 0..100 {
    let permit = semaphore.clone().acquire_owned().await.unwrap();
    let handle = tokio::spawn(async move {
    drop(permit);  // release permit when done
    
    // work
});
    handles.push(handle);
}
```

### Periodic Tasks (Interval)

```rust
let mut interval = tokio::time::interval(Duration::from_secs(60));
interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

loop {
    interval.tick().await;   // waits for next interval, accounts for drift
    do_periodic_work().await;
}
```

### Backpressure with bounded channels

Use bounded `mpsc` channels to apply backpressure — when the channel is full, `send().await` blocks until a slot opens. This prevents fast producers from overwhelming slow consumers.

```rust
// Producer blocks when channel full — natural backpressure
let (tx, mut rx) = tokio::sync::mpsc::channel::<i32>(1000);
```

## Testing Async Code

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_async_function() {
        let result = async_fn().await;
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn test_deterministic() {
        // current-thread for deterministic tests
    }

    #[tokio::test(shared = false)]
    async fn test_isolated() {
        // each test gets its own runtime
    }
}
```

For mocking async traits, use `mockall` (add `#[automock]` to traits, works with async-traits for boxed futures).

## Common Pitfalls

1. **Blocking the async thread.** Calling blocking I/O (std::fs, std::net, heavy CPU) inside an async function blocks the runtime thread. Use `spawn_blocking` for blocking operations:

```rust
tokio::task::spawn_blocking(|| {
    std::fs::read_to_string("large_file.csv")  // blocking — fine in spawn_blocking
}).await;
```

2. **Holding a std::sync::Mutex across `.await`.** This blocks the entire thread. Use tokio::sync::Mutex.

3. **Spawning tasks that borrow from the stack.** `tokio::spawn` requires `'static`. If you need to reference something with a shorter lifetime, structure the ownership so the task owns the data, or use `select!`/`join!` without spawning.

4. **Forgetting to `.await` a future.** Async functions return a future — calling them without `.await` does nothing. This compiles but silently does no work.

```rust
async fn do_work() { /* ... */ }
fn main() {
    do_work();   // BUG — creates future, drops it immediately, nothing runs
}
```

5. **Using `select!` without understanding fairness.** `select!` polls branches in declaration order. A branch that's always ready can starve others.

6. **Ignoring cancellation.** Tasks can be cancelled at any `.await` point. Code after the `.await` that was cancelled does not run. Design for this.

7. **Using unbounded channels in production without monitoring.** Unbounded channels can grow unbounded under load and OOM the process. Prefer bounded with explicit backpressure.

8. **Concurrent mutation without synchronization.** Async doesn't make data races impossible. Mutating shared state across tasks without Mutex/RwLock is UB (in the data-race sense, not memory safety — Rust's borrow checker prevents data races on references, but `Cell`/`RefCell` interior mutability needs care with `Send`).

9. **Recursive async without depth limit.** Spawning a new task that spawns another task indefinitely → resource exhaustion. Add limits.

10. **Using `block_on` inside async code.** `runtime.block_on(future)` inside an async function that's already running on a runtime causes a panic (or deadlock in current-thread runtime). Use `spawn` or `spawn_blocking` instead.

## Verification Checklist

- [ ] Can set up `#[tokio::main]` and explain multi-thread vs current-thread
- [ ] Can spawn a task and await its `JoinHandle`, handling `JoinError`
- [ ] Can explain why `tokio::spawn` requires `Send + 'static`
- [ ] Can use `tokio::select!` for racing futures and handling cancellation
- [ ] Can pass data between tasks with `mpsc`, `broadcast`, `watch`, `oneshot` channels
- [ ] Can choose the right channel type for a given communication pattern
- [ ] Can use `tokio::sync::Mutex` and explain when to prefer it over `std::sync::Mutex`
- [ ] Can use `spawn_blocking` for blocking I/O / CPU work inside async
- [ ] Can implement graceful shutdown with `CancellationToken` and `select!`
- [ ] Can write a periodic task with `tokio::time::interval`
- [ ] Can use `tokio::try_join!` for fail-fast concurrent operations
- [ ] Can write async tests with `#[tokio::test]`
- [ ] Understands that async does not parallelize CPU work, and uses rayon/threads for that

## One-Shot Recipes

### HTTP fetch with timeout + error handling

```rust
async fn fetch_with_timeout(url: &str, timeout: Duration) -> Result<String, Error> {
    let client = reqwest::Client::builder()
        .timeout(timeout)
        .build()?;
    let resp = client.get(url).send().await?;
    let text = resp.text().await?;
    Ok(text)
}
```

### Concurrent fetch with fail-fast

```rust
async fn fetch_all(urls: &[&str]) -> Result<Vec<String>, Error> {
    let tasks: Vec<_> = urls.iter()
        .map(|&url| fetch_with_timeout(url, Duration::from_secs(5)))
        .collect();
    tokio::try_join_all(tasks).await
}
```

### Graceful server shutdown

```rust
async fn run_server(shutdown: CancellationToken) {
    loop {
        tokio::select! {
            _ = shutdown.cancelled() => return,
            conn = accept() => { handle(conn).await; }
        }
    }
}
```

### Run blocking code without blocking the runtime

```rust
async fn read_large_file(path: &str) -> Result<String, Error> {
    let content = tokio::task::spawn_blocking(|| {
        std::fs::read_to_string(path)
    }).await??;
    Ok(content)
}
```
