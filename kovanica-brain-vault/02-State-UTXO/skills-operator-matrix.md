---
source: skills/operator-matrix/SKILL.md
name: operator-matrix
synced_at: 2026-09-12T08:33:08.794406+00:00
synced_from: skills
tags: [skill, kovanica]
---
# operator-matrix — synced from skills/operator-matrix/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.794406+00:00

# Operator vs Participant Matrix

Clear guidance on which `KOVANICA_*` flags are appropriate for each role.

| Variable / Role            | Home participant | Public explorer / API | Seed node | Mining / producer node |
|----------------------------|------------------|-----------------------|-----------|------------------------|
| `KOVANICA_POW`             | 1                | 1                     | 1         | 1                      |
| `KOVANICA_MINE`            | 0                | 0                     | 0         | 1 (if intentional)     |
| `KOVANICA_MINE_SECS`       | 120              | 120                   | 120       | ≥ 120                  |
| `KOVANICA_FAUCET`          | 0                | 0                     | 0         | 0                      |
| `KOVANICA_ALLOW_RESET`     | 0                | 0                     | 0         | 0                      |
| `KOVANICA_OPERATOR`        | 0                | 0 or 1 (UI only)      | 0         | 0                      |
| `KOVANICA_LISTEN`          | 0.0.0.0:9000 (optional) | 0.0.0.0:9000     | 0.0.0.0:9000 | 0.0.0.0:9000        |
| `KOVANICA_PEERS`           | seed.kovanica.online:9000 | seed…            | **off**   | seed…                  |
| `KOVANICA_DATA`            | persistent       | persistent            | persistent| persistent             |

## Rules of thumb

- **Never** enable `ALLOW_RESET` or open `FAUCET` on any node that is reachable from the public internet.
- Seed nodes must not dial themselves (`KOVANICA_PEERS=off` or empty).
- Home users only need outbound 9000; inbound is optional.
- After RFC-006 activation the same matrix still applies — the economic changes do not relax operator safety flags.
- Document the exact flag set in every run script or systemd unit you produce.
