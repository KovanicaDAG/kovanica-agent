---
source: skills/api-reference/SKILL.md
name: api-reference
synced_at: 2026-09-12T08:33:08.791886+00:00
synced_from: skills
tags: [skill, kovanica]
---
# api-reference — synced from skills/api-reference/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.791886+00:00

# Kovanica HTTP API Reference

All endpoints are available on both the public explorer (`https://explorer.kovanica.online`) and a local node (`http://127.0.0.1:8080` when run in explorer mode). The wallet app proxies the public explorer (CORS is closed on the node itself).

## Live Chain Parameters (always verify with /api/head)

### Pre-RFC-006 shape (current public testnet)

```json
{
  "network": "kovanica-testnet",
  "genesis": "3beecbebb6103ee24d1617fd87e920c949d613febbbcf6ca1453f3a4bf74056e",
  "tip": "<current tip hash>",
  "blocks": 6577,
  "min_fee": 40000,
  "atom": 100000000
}
```

### Post-RFC-006 shape (expected after activation + Step 7)

```json
{
  "network": "kovanica-testnet",
  "genesis": "<new genesis after reset>",
  "tip": "<current tip hash>",
  "blocks": <height>,
  "atom": 100000000,
  "min_fee": <dynamic, tracks subsidy>,
  "subsidy": <subsidy_at(height) in atoms>,
  "native_minted": <cumulative minted atoms>,
  "total": <same as native_minted or alias>,
  "circulating": <total − immature − unvested treasury>,
  "burned": <cumulative 75 % fee burn>
}
```

Detection rule: if `subsidy` / `native_minted` / `burned` fields are present → treat as post-RFC-006 network.

- 1 KVNC = 100_000_000 atoms
- GHOSTDAG k = 3
- After activation the fee floor becomes `max(1, subsidy / 500_000)` atoms per byte.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/head | Network, genesis, tip, height, atom, min_fee + (post-RFC-006) subsidy / supply fields |
| GET | /api/bootstrap | Listen address, peers, upstream probe |
| GET | /api/p2p | TCP listen + bootstrap peers |
| GET | /api/blocks | Octet-stream full block dump (used for clone catch-up) |
| GET | /api/state | Full DAG + flags |
| GET | /api/utxos?address=<addr> | Spendable UTXOs for address (immature coinbases excluded by node) |
| GET | /api/history?address=<addr> | Address deltas / history |
| GET | /api/origins | ISO3 origin pulses |
| GET | /api/spec | Plain-text technical spec |
| POST | /api/prepare | Build unsigned tx → returns sighash + fee + change |
| POST | /api/submit | Broadcast fully signed transaction |
| POST | /api/produce | Pack mempool into a block template |
| POST | /api/mine | Mine a coinbase block (only when enabled) |
| POST | /api/faucet | Testnet faucet (disabled on public explorer) |
| POST | /api/origin | Record a country origin pulse |

## Transaction Flow (client-side signing)

1. **Prepare**  
   `POST /api/prepare` with inputs/outputs.  
   Response contains:
   - sighash bytes (or hex)
   - calculated fee (respects current fee floor)
   - change output (if any)  
   The node already skips immature coinbases when selecting inputs.

2. **Sign offline**  
   Sign the raw sighash with Ed25519.  
   Result must be a 64-byte signature → 128 hex characters.  
   Nodes only accept 64-byte Ed25519 signatures.

3. **Submit**  
   `POST /api/submit` with the completed signed transaction.  
   The node never receives the private key or seed phrase.

## Post-RFC-006 Error Conditions Clients Must Handle

| Error | Meaning | Client action |
|-------|---------|---------------|
| `LedgerError::SupplyCapExceeded` | Coinbase would push `native_minted` over `MAX_SUPPLY` | Do not retry the same coinbase claim; surface "supply cap reached" |
| `LedgerError::CoinbaseImmature` | Attempt to spend a coinbase younger than 100 blocks | Wait until `height >= created_at + 100`; refresh UTXO set |

`/api/prepare` should never return immature coinbases, but defensive clients still check maturity before building transactions offline.

## Fee Rules After Activation

- Floor = `max(1, subsidy_at(height) / 500_000)` atoms per byte.
- 75 % of every fee is burned (unclaimable by the producer).
- Producer may claim at most `subsidy + total_fees / 4`.
- Clients should estimate fees using the live `subsidy` (or `min_fee`) from `/api/head` rather than any hard-coded constant.

## Important Security Notes

- All signing happens in the browser / client (wallet, CLI, or custom tool).
- Never send seed phrases or private keys to any `/api/*` endpoint.
- Public explorer keeps reset and open faucet disabled.
- Prefer DNS-only seed names (`seed.kovanica.online`) for P2P; Cloudflare orange-cloud names do not forward TCP 9000.
- After the RFC-006 testnet reset, all prior balances are gone — treat addresses as new.
