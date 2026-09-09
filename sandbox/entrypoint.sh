#!/usr/bin/env bash
# Second line of defense: even if agent-api's Python whitelist check is ever
# bypassed or buggy, this script refuses to run anything but the four
# allowed cargo subcommands. Defense in depth, not decoration.
set -euo pipefail

ALLOWED_COMMANDS=("check" "test" "clippy" "build")
CMD="${1:-}"

if [[ -z "$CMD" ]]; then
  echo "ERROR: no cargo subcommand given" >&2
  exit 1
fi

allowed=false
for c in "${ALLOWED_COMMANDS[@]}"; do
  if [[ "$CMD" == "$c" ]]; then
    allowed=true
    break
  fi
done

if [[ "$allowed" != "true" ]]; then
  echo "ERROR: '$CMD' is not whitelisted. Allowed: ${ALLOWED_COMMANDS[*]}" >&2
  exit 126
fi

# Reject any argument that smells like a shell-out attempt.
for arg in "$@"; do
  if [[ "$arg" =~ (rm|sudo|curl|wget|;|\||&|\$\(|\`) ]]; then
    echo "ERROR: rejected suspicious argument: $arg" >&2
    exit 126
  fi
done

exec cargo "$@" --offline
