# Ephemeral, per-request sandbox for running cargo against the Kovanica repo.
# Never run this container long-lived. agent-api spawns one instance per
# cargo call, with --rm, then throws it away.
#
# Recommended host runtime: gVisor (runsc) or Sysbox instead of plain runc.
# Set at spawn time (docker SDK: `runtime="runsc"`), not here — the runtime
# is a host-level flag, not something the image controls.

# Pin to a Rust that matches the repo's reality: Cargo.lock pulls blake3
# 1.8.6, whose manifest uses edition-2024 (stabilized in Cargo 1.85+), so
# older images fail at `cargo fetch` manifest parse. 1.98 matches the
# toolchain the workspace builds with in CI (dtolnay/rust-toolchain@stable).
FROM rust:1.98-slim-bookworm

RUN groupadd -r sandbox && useradd -r -g sandbox -m -d /home/sandbox sandbox

# Minimal build deps only. Deliberately no curl/wget/ssh/git — this container
# runs with network_disabled=True, so network tools have no legitimate use
# and only help an escape attempt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Pre-vendor dependencies at image build time (network allowed here, at
# build time only) so requests can run fully offline via `cargo ... --offline`
# (see entrypoint.sh). Kovanica workspace layout (Cargo.toml
# [workspace.members]): kovanica-dag, kovanica-state, kovanica-node,
# kovanica-ffi, kovanica-cli — copy manifests only (no src/) so `cargo fetch`
# resolves the full dep graph without invalidating the Docker layer cache on
# every source change.
#
# Build context MUST be the kovanica-protocol repo root, not this
# sandbox/ directory, since Cargo.toml and crates/ only exist there.
# Via compose (context set in docker-compose.yml's sandbox-image service):
#   docker compose --profile build-only build sandbox-image
# Manually, from the repo root:
#   docker build -f kovanica-agent/sandbox/Dockerfile -t kovanica-sandbox:latest .
# NOTE: keep this crate list in sync with Cargo.toml's [workspace.members]
# and AGENTS.md's repository layout section if either changes.
COPY Cargo.toml Cargo.lock /workspace/
COPY crates/kovanica-dag/Cargo.toml /workspace/crates/kovanica-dag/Cargo.toml
COPY crates/kovanica-state/Cargo.toml /workspace/crates/kovanica-state/Cargo.toml
COPY crates/kovanica-node/Cargo.toml /workspace/crates/kovanica-node/Cargo.toml
COPY crates/kovanica-ffi/Cargo.toml /workspace/crates/kovanica-ffi/Cargo.toml
COPY crates/kovanica-cli/Cargo.toml /workspace/crates/kovanica-cli/Cargo.toml
RUN set -eux; \
    for crate in kovanica-dag kovanica-state kovanica-node kovanica-ffi kovanica-cli; do \
      dir=/workspace/crates/$crate; \
      mkdir -p $dir/src $dir/benches $dir/examples; \
      echo "fn main() {}" > $dir/src/main.rs; \
      echo "// placeholder for cargo fetch" > $dir/src/lib.rs; \
      # create placeholder files for every declared [[bench]] (default
      # path benches/<name>.rs) and [[example]] (examples/<name>.rs) so
      # `cargo fetch` can parse the manifest — cargo validates target
      # paths even when it only needs the dependency graph. The name= line
      # follows the section header directly (no path= override in these
      # manifests today; if one appears, this still creates the default
      # path, which is enough for fetch).
      awk '/^\[\[bench\]\]/{s="bench"} /^\[\[example\]\]/{s="example"} /^name *=/{n=$3; gsub(/"/,"",n); if (s=="bench") printf "benches/%s.rs\n", n; else if (s=="example") printf "examples/%s.rs\n", n; s=""}' $dir/Cargo.toml | while read f; do \
        mkdir -p $dir/$(dirname $f); \
        echo "fn main() {}" > $dir/$f; \
      done; \
    done; \
    cd /workspace && cargo fetch --locked; \
    find /workspace/crates \( -path "*/src/*.rs" -o -path "*/benches/*.rs" -o -path "*/examples/*.rs" \) -delete

COPY kovanica-agent/sandbox/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    chown -R sandbox:sandbox /home/sandbox

WORKDIR /workspace
USER sandbox

ENV CARGO_HOME=/home/sandbox/.cargo \
    CARGO_TARGET_DIR=/tmp/target

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
