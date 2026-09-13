---
source: skills/rfc-006-activation/SKILL.md
name: rfc-006-activation
synced_at: 2026-09-12T08:33:08.796097+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-006-activation — synced from skills/rfc-006-activation/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.796097+00:00

# RFC-006 Activation & Testnet-Reset Playbook

> Status: Steps 1–4 landed on branch `tokenomics/rfc-006-emission-curve`.  
> Steps 5–6 (treasury genesis + mainnet profile) and Step 7 (supply accounting) pending.  
> Activation is a **consensus fork** → the public testnet **resets**.

## What Changes at Activation

| Area                    | Pre-RFC-006                          | Post-RFC-006                                      |
|-------------------------|--------------------------------------|---------------------------------------------------|
| Emission                | Older schedule / higher subsidy      | Smooth geometric: s₀=10 KVNC, E=2M, α=3/4         |
| Hard cap                | None / soft                          | `MAX_SUPPLY = 90.2M KVNC` enforced via `native_minted` |
| Coinbase maturity       | None or different                    | Exactly 100 blocks (`COINBASE_MATURITY`)          |
| Fee model               | Flat or older floor                  | Floor = `max(1, subsidy/500_000)` atoms/byte; 75% burned / 25% to producer |
| Checkpoint format       | v6                                   | v7 (+ coinbase flag per output, `native_minted` counter) |
| Genesis                 | Current genesis                      | New genesis with premine 0.2M + 10×1M treasury vaults |
| All prior balances      | Valid                                | **Wiped** (testnet reset)                         |

## Detection: Pre vs Post Network

Always call `GET /api/head` and inspect:

```text
Post-RFC-006 indicators (expected once activated):
- presence of fields: subsidy, native_minted / total, circulating, burned
- min_fee that tracks the current subsidy (not a static 40000)
- genesis hash different from the pre-RFC-006 value
  (old: 3beecbebb6103ee24d1617fd87e920c949d613febbbcf6ca1453f3a4bf74056e)
```

Until the new fields appear, treat the network as pre-RFC-006 and do **not** hard-code the new economic constants into production clients.

## Client / Wallet Impact Checklist

After activation every client **must**:

1. Re-fetch `/api/head` and stop using any cached min_fee / subsidy.
2. Skip immature coinbases (created_at + 100 > current height) when selecting inputs.
3. Respect the dynamic fee floor (`max(1, subsidy / 500_000)` atoms per byte).
4. Expect `/api/prepare` to return fees calculated under the new rules.
5. Handle new ledger errors:
   - `LedgerError::SupplyCapExceeded`
   - `LedgerError::CoinbaseImmature`
6. Display supply metrics (`total`, `circulating`, `burned`) when the API exposes them.
7. Treat all pre-reset addresses/balances as gone — no migration path for testnet funds.

## Node Operator Checklist

- Wipe or move aside the old `KOVANICA_DATA` directory (new genesis will be written).
- Rebuild from the branch that contains the merged RFC-006 changes.
- Confirm checkpoint version is v7 after first start.
- Keep `KOVANICA_ALLOW_RESET=0` and `KOVANICA_FAUCET=0` on public nodes.
- Seed nodes: set `KOVANICA_PEERS=off` and use DNS-only names for clones.
- After restart, verify:
  ```sh
  curl -s http://127.0.0.1:8080/api/head
  # genesis, subsidy, native_minted / total should match the new RFC-006 values
  ```

## Tooling & Script Guidance

- Any hard-coded constants (old subsidy, old min_fee, old genesis) become bugs at activation.
- Prefer live `/api/head` values over compile-time constants.
- Emission math helpers (see `emission-math/SKILL.md`) should be used by explorers and wallets that need to show "next era subsidy" or "remaining issuance".
- The `scripts/check-head.sh` helper remains useful — after reset it will show the new genesis.

## Remaining Implementation Steps (from RFC)

| Step | Description                          | Status   |
|------|--------------------------------------|----------|
| 1–4  | Emission curve, MAX_SUPPLY, maturity, fee burn | Landed & green (785 tests) |
| 5    | Treasury genesis (10×1M vaults)      | Pending  |
| 6    | Mainnet profile                      | Pending  |
| 7    | Supply accounting / observability    | Pending  |

Do not declare the economic model "live on public testnet" until steps 5–7 are also merged and the reset has occurred.

## Safety Notes for Conversations

- Always warn that activation wipes the current testnet.
- Never assume old balances or old fee numbers survive.
- When generating client code, include explicit handling for the two new ledger errors and for immature coinbases.
- Point users to this file whenever they ask about "when the new tokenomics go live" or "what breaks at activation".
