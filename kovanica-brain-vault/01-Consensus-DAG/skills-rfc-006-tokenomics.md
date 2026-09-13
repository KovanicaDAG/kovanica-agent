---
source: skills/rfc-006-tokenomics/SKILL.md
name: rfc-006-tokenomics
synced_at: 2026-09-12T08:33:08.796409+00:00
synced_from: skills
tags: [skill, kovanica]
---
# rfc-006-tokenomics — synced from skills/rfc-006-tokenomics/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.796409+00:00

# Kovanica Tokenomics — RFC-006

**Status (as of the provided RFC):** consensus changes partially implemented on
`tokenomics/rfc-006-emission-curve`. Steps 1–4 (smooth emission curve,
`MAX_SUPPLY` hard cap, coinbase maturity, fee burn) are landed and green
(785 tests). Steps 5–6 (treasury genesis + mainnet profile) and Step 7
(supply accounting / observability) are pending. Full spec is this document.

## 1. Motivation & goals

1. **Predictable, capped supply.** Total native KVNC hard-capped below 100M.
2. **Long-tail, fair emission.** Smooth geometric decay per era (no abrupt halvings).
3. **Security budget.** Block rewards (subsidy + fee share) fund PoW and VRF-staked validation.
4. **Deflationary fee market.** Majority of every transaction fee is burned.

## 2. Units

- **1 KVNC = 10⁸ atoms** (`ATOM = 100_000_000`).
- All consensus amounts are `u64` atom counts.
- Human-facing amounts in KVNC; wire/ledger amounts in atoms.

## 3. Emission curve

Smooth geometric decay:

- Genesis subsidy **s₀ = 10 KVNC/block**.
- Era length **E = 2,000,000 blocks**.
- Per-era decay **α = 3/4**: `s(era) = s(era−1) × 3/4` (integer floor).
- `subsidy_at(height) = s(height / E)`; eras ≥ 256 return 0.

Closed-form total emission:

```
total_emission = s₀ · E / (1 − α) = 10 × 2,000,000 × 4 = 80,000,000 KVNC
```

### Era table (selected)

| Era | Subsidy (KVNC) | Era emission (M KVNC) | Cumulative (M KVNC) |
|-----|----------------|-----------------------|---------------------|
| 0   | 10.000         | 20.00                 | 20.00               |
| 1   | 7.500          | 15.00                 | 35.00               |
| 2   | 5.625          | 11.25                 | 46.25               |
| 3   | 4.219          | 8.44                  | 54.69               |
| 4   | 3.164          | 6.33                  | 61.02               |
| 5   | 2.373          | 4.75                  | 65.76               |
| …   | → 0            | → 0                   | → 80.00             |

At ~1 block/s the first era lasts ≈ 23 days; the tail extends for decades.

## 4. Terminal supply & hard cap

- `MAX_SUPPLY = 90.2M KVNC = 90_200_000_000_000_000 atoms`.
- Enforced by per-block cumulative `native_minted` counter.
- A coinbase that would push `native_minted + claimed > MAX_SUPPLY` is rejected (`LedgerError::SupplyCapExceeded`).
- Genesis records premine + treasury as the initial `native_minted`.
- Counter serialized in checkpoint v7.

## 5. Distribution

| Component        | Amount    | Mechanism                                        |
|------------------|-----------|--------------------------------------------------|
| Founder premine  | 0.2M KVNC | Genesis coinbase output (existing 200 KVNC)      |
| Treasury         | 10M KVNC  | 10 × 1M RFC-005 vault tranches at genesis        |
| Curve emission   | 80M KVNC  | Block subsidies over the emission schedule       |
| **Total**        | **90.2M KVNC** | **< 100M**                                  |

### Treasury vesting

10 vault tranches of 1M KVNC each (RFC-005 time-lock vault composition):

- Tranche *k* (k = 1..=10): `VaultScript` with `absolute_time = k × 31,536,000` (≈ k years at 1 block/s).
- Beneficiary (CLAIM after expiry) = treasury.
- Owner (RECOVER before expiry) = treasury governance.
- Keys are currently placeholders pending a real key ceremony before mainnet.

## 6. Block subsidy & coinbase maturity

- Coinbase may claim up to `subsidy_at(height)` + fee share.
- **Coinbase maturity: `COINBASE_MATURITY = 100` blocks.**
- Spendable only at `height >= created_at + 100`; earlier spends rejected (`LedgerError::CoinbaseImmature`).
- Applies to all coinbase outputs (premine, treasury, subsidies).
- Transaction builder skips immature coinbases.

## 7. Fees

- **Fee floor:** `max(1, subsidy / 500_000)` atoms per byte.
- **Fee burn (75/25):** 75% of every transaction fee is burned; 25% goes to the block producer.
- Implementation: coinbase allowance = `subsidy + total_fees / 4` (integer division). Excess is unclaimable → destroyed. No special burn opcode or wire-format change.

## 8. Staking incentives & security budget

- Security budget per block = **subsidy + 25% of fees**.
- Hybrid admission (Stage 3): PoW blocks require real hash work; VRF-staked blocks require stake-weighted sortition.
- GHOSTDAG blue work (real PoW) remains the chain-selection work source.
- Bonded validators earn the same block reward as PoW miners when they win a slot.
- 10M treasury provides long-term development budget independent of declining subsidy.

## 9. Supply accounting

| Metric       | Definition                                                        |
|--------------|-------------------------------------------------------------------|
| `total`      | `native_minted` — cumulative minted (curve + premine + treasury)  |
| `circulating`| `total` − immature coinbases − unvested treasury tranches         |
| `burned`     | cumulative 75% fee burn                                           |

- `/api/head` will report subsidy, issuance, supply, and related fields.
- Prometheus: `kovanica_supply_total`, `kovanica_supply_circulating`, `kovanica_supply_minted`, `kovanica_supply_burned`.

## 10. Activation & migration

- Consensus fork. Testnet **resets** at activation.
- Checkpoint v6 → v7: per-output coinbase flag + `native_minted` counter.
- No transaction wire-format bump; sighash domain untouched.

## 11. Open questions & non-goals

- Treasury key ceremony required before mainnet.
- Mainnet profile parameters filled but dormant until RFC review/approval.
- Fee floor constant may be tuned from soak data.
- Non-goals: no rebasing, no demurrage, no algorithmic price stabilization, no governance token. KVNC is a pure ledger asset with a fixed, published issuance schedule.
