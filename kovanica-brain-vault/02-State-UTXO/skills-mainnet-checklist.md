---
source: skills/mainnet-checklist/SKILL.md
name: mainnet-checklist
synced_at: 2026-09-12T08:33:08.793965+00:00
synced_from: skills
tags: [skill, kovanica]
---
# mainnet-checklist — synced from skills/mainnet-checklist/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.793965+00:00

# Mainnet Readiness Checklist

Use this before any mainnet parameter freeze or launch announcement.

## Consensus & economics (must be locked)

- [ ] RFC-006 fully merged (steps 5–7 included: treasury genesis, mainnet profile, supply accounting)
- [ ] Testnet reset completed and soaked for ≥ 2 weeks with no supply-cap or maturity bugs
- [ ] `MAX_SUPPLY`, era length, α, coinbase maturity, fee floor constant reviewed and frozen
- [ ] Treasury key ceremony completed; placeholder keys removed
- [ ] Checkpoint v7 (or later) is the only format on the network
- [ ] GHOSTDAG `k` value confirmed for mainnet (currently 3 on testnet)

## Networking & ops

- [ ] Multiple independent seed nodes (DNS-only / grey-cloud) with documented IPs
- [ ] P2P on TCP 9000 proven under partition and high-latency conditions
- [ ] No reliance on Cloudflare-proxied hostnames for P2P
- [ ] Operator flags (`ALLOW_RESET`, open faucet) impossible to enable on public binaries or clearly gated
- [ ] Monitoring: Prometheus series for supply, tip, peer count, orphan rate

## Clients & ecosystem

- [ ] Official wallet + CLI handle post-RFC-006 `/api/head` fields and new ledger errors
- [ ] Immature coinbase filtering verified in all official clients
- [ ] Multisig (KVP-101), multi-asset (KVP-102), vaults (KVP-105) smoke-tested on the reset testnet
- [ ] Mobile APK/IPA and light-node/FFI paths tested against mainnet genesis parameters
- [ ] Documentation (site, `/docs`, roadmap) updated to mainnet numbers

## Security & process

- [ ] External review or audit of consensus-critical paths (emission, cap, maturity, script machine)
- [ ] Responsible-disclosure contact published
- [ ] Genesis block hash and parameters published in multiple independent places before launch
- [ ] Clear statement that testnet balances do not carry over

## Go / no-go

Do **not** announce mainnet until every box above is checked and the final genesis is reproducible by at least two independent parties.
