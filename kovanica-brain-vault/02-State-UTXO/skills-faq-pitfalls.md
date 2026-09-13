---
source: skills/faq-pitfalls/SKILL.md
name: faq-pitfalls
synced_at: 2026-09-12T08:33:08.793126+00:00
synced_from: skills
tags: [skill, kovanica]
---
# faq-pitfalls — synced from skills/faq-pitfalls/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.793126+00:00

# FAQ & Common Pitfalls

## Networking

**Q: My node won't sync.**  
A: Use `seed.kovanica.online:9000` (DNS-only / grey-cloud). Never point `KOVANICA_PEERS` at `explorer.kovanica.online:9000` — Cloudflare does not forward TCP 9000.

**Q: Do I need inbound 9000 open?**  
A: Only if you want to serve other peers. Outbound to the seed is enough to catch up.

## Economics (RFC-006)

**Q: Why is there a hard cap if the curve already sums to 80 M?**  
A: In a DAG, parallel blocks in each other's anticone can each mint a full subsidy. `native_minted` + `MAX_SUPPLY` (90.2 M) is the real ceiling.

**Q: When can I spend a coinbase?**  
A: Only after 100 blocks (`COINBASE_MATURITY`). The node's `prepare` already skips immature outputs; clients should too.

**Q: Who gets the fees?**  
A: 25 % to the block producer, 75 % burned (unclaimable). There is no burn opcode — the coinbase allowance is simply capped.

**Q: Will my testnet coins survive the RFC-006 activation?**  
A: No. Activation is a consensus fork that resets the testnet.

## Keys & signing

**Q: Does the node ever see my seed?**  
A: No. Signing is client-side (browser, CLI, or your own tool). Only the 64-byte Ed25519 signature (128 hex) is submitted.

**Q: What is the sighash?**  
A: The bytes returned by `POST /api/prepare`. Sign those exact bytes; do not re-serialize the transaction yourself unless you match the node's encoding 1:1.

## Multi-asset & scripts

**Q: Is KVP-102 an ERC-20?**  
A: No. It is a native multi-asset UTXO model with per-asset conservation.

**Q: Can I use arbitrary Bitcoin Script?**  
A: No. Script v2 (RFC-003) is a bounded machine (CLTV/CSV/hash-lock, etc.). Keep scripts inside that model.

## Operator flags

**Q: Can I turn on the faucet or reset on a public node?**  
A: You can, but you must not. Keep `KOVANICA_FAUCET=0` and `KOVANICA_ALLOW_RESET=0` on anything reachable from the internet.
