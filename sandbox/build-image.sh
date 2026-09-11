#!/bin/bash
# Build the kovanica-agent sandbox image from a STANDALONE kovanica-agent
# checkout (not inside the protocol tree).
#
# Needs KOVANICA_PROTOCOL_ROOT pointing at a kovanica-protocol checkout
# (default ../kovanica-protocol relative to this script) so the Dockerfile's
# pre-vendoring step can COPY Cargo.toml + each crate's Cargo.toml.
#
# Usage (standalone kovanica-agent checkout):
#   KOVANICA_PROTOCOL_ROOT=/path/to/kovanica-protocol ./sandbox/build-image.sh
#   OR (if checked out inside the protocol tree at kovanica-protocol/kovanica-agent/):
#   ./sandbox/build-image.sh   (resolves .. automatically)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PROTOCOL_ROOT="${KOVANICA_PROTOCOL_ROOT:-$AGENT_ROOT/..}"
if [[ ! -f "$PROTOCOL_ROOT/Cargo.toml" ]]; then
  echo "error: protocol checkout not found at $PROTOCOL_ROOT" >&2
  echo "  set KOVANICA_PROTOCOL_ROOT=/path/to/kovanica-protocol" >&2
  exit 1
fi

cd "$PROTOCOL_ROOT"
echo "==> building kovanica-sandbox:latest from $AGENT_ROOT/sandbox/Dockerfile"
docker build -f "$AGENT_ROOT/sandbox/Dockerfile" -t kovanica-sandbox:latest .
echo "==> done: kovanica-sandbox:latest"
