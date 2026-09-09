#!/usr/bin/env bash
# Build kovanica-sandbox:latest for a STANDALONE kovanica-agent checkout.
#
# The sandbox Dockerfile pre-vendors the protocol workspace's Cargo.lock so
# requests can run fully offline, and its COPY lines read the workspace
# manifests from the build context. When kovanica-agent lives inside the
# protocol repo tree the compose file's `context: ..` handles that; from a
# standalone checkout there is no parent Cargo.toml, so this script copies
# the manifests it needs into a throwaway context and builds from there.
#
# Requires KOVANICA_PROTOCOL_ROOT (default: ../kovanica-protocol) pointing at
# a kovanica-protocol checkout. Network is required here (build time only);
# the produced image runs with network_disabled=True via sandbox-runner.
set -euo pipefail

PROTOCOL_ROOT="${KOVANICA_PROTOCOL_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTEXT_DIR="$(mktemp -d)"
trap 'rm -rf "$CONTEXT_DIR"' EXIT

if [[ ! -f "$PROTOCOL_ROOT/Cargo.toml" || ! -d "$PROTOCOL_ROOT/crates" ]]; then
    echo "error: KOVANICA_PROTOCOL_ROOT ($PROTOCOL_ROOT) is not a kovanica-protocol checkout" >&2
    exit 1
fi

# Workspace root manifests + per-crate manifests (the Dockerfile COPYs
# crates/kovanica-*/Cargo.toml — keep in sync with that COPY list).
cp "$PROTOCOL_ROOT/Cargo.toml" "$PROTOCOL_ROOT/Cargo.lock" "$CONTEXT_DIR/"
for crate in kovanica-dag kovanica-state kovanica-node kovanica-ffi kovanica-cli; do
    mkdir -p "$CONTEXT_DIR/crates/$crate"
    cp "$PROTOCOL_ROOT/crates/$crate/Cargo.toml" "$CONTEXT_DIR/crates/$crate/Cargo.toml"
done

# The Dockerfile copies placeholder benches for any declared [[bench]]; the
# per-crate benches/ dirs are otherwise empty and get created by the RUN step.
cp "$SCRIPT_DIR/Dockerfile" "$CONTEXT_DIR/Dockerfile"

docker build -t kovanica-sandbox:latest "$CONTEXT_DIR"
echo "kovanica-sandbox:latest built from protocol checkout at $PROTOCOL_ROOT"