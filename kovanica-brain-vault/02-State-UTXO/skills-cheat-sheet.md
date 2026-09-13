---
source: skills/cheat-sheet/SKILL.md
name: cheat-sheet
synced_at: 2026-09-12T08:33:08.792522+00:00
synced_from: skills
tags: [skill, kovanica]
---
# cheat-sheet — synced from skills/cheat-sheet/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.792522+00:00

# Kovanica Cheat Sheet

## One-liners

```bash
# Install node
curl -sSfL https://raw.githubusercontent.com/KovanicaDAG/kovanica-node/main/scripts/install.sh | bash

# Participant node
export KOVANICA_POW=1 KOVANICA_MINE=0 KOVANICA_FAUCET=0 KOVANICA_ALLOW_RESET=0
export KOVANICA_OPERATOR=0 KOVANICA_LISTEN=0.0.0.0:9000
export KOVANICA_PEERS=seed.kovanica.online:9000 KOVANICA_DATA=$PWD/data
./target/release/kovanica-node explorer 127.0.0.1:8080

# Check sync
curl -s http://127.0.0.1:8080/api/head
curl -s https://explorer.kovanica.online/api/head
```

## Constants (RFC-006)

| Name | Value |
|------|-------|
| ATOM | 100_000_000 |
| S0 | 10 KVNC / block |
| ERA_LENGTH | 2_000_000 blocks |
| α | 3/4 per era |
| MAX_SUPPLY | 90.2 M KVNC |
| Premine | 0.2 M |
| Treasury | 10 M (10×1 M vaults) |
| Curve emission | 80 M |
| COINBASE_MATURITY | 100 blocks |
| Fee split | 75 % burn / 25 % producer |
| Fee floor | max(1, subsidy/500_000) atoms/byte |
| k (GHOSTDAG) | 3 |
| P2P | TCP :9000 only |

## Transaction flow

1. `POST /api/prepare` → sighash + fee + change  
2. Sign sighash with Ed25519 → 128 hex  
3. `POST /api/submit`

## Key URLs

- Site: https://kovanica.online  
- Explorer: https://explorer.kovanica.online  
- Wallet: https://wallet.kovanica.online  
- Roadmap: https://kovanica.online/roadmap  
- Node: https://github.com/KovanicaDAG/kovanica-node  
- Seed: `seed.kovanica.online:9000` (grey-cloud)
