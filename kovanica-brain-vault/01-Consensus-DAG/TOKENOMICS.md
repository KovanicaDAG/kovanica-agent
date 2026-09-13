# KVNC tokenomics (RFC-006)

Numbers match the RFC-006 reference implementation in `kovanica-state` and
`kovanica-node`. If code and this doc diverge, **code wins**.

**Network:** `kovanica-testnet` (mainnet profile filled but dormant).

> **Activation note:** Switching a live network to RFC-006 is a consensus fork
> and requires a **testnet reset**.

---

## Units

| Symbol | Meaning |
|--------|--------|
| **KVNC** | Native currency ticker |
| **atom** | Smallest unit |
| **Decimals** | 8 |
| **1 KVNC** | `100_000_000` atoms (`ATOM`) |

---

## Emission (smooth geometric curve)

| Parameter | Value |
|-----------|--------|
| Genesis subsidy \(s_0\) | **10 KVNC** per block |
| Era length \(E\) | **2_000_000** blocks |
| Decay \(\alpha\) | **3/4** per era (integer floor) |
| Curve total | **80_000_000 KVNC** |

```text
era = floor(height / 2_000_000)
s(era) = floor(s(era-1) * 3/4)   with s(0) = 10 KVNC
```

---

## Hard cap & distribution

| Component | Amount | Mechanism |
|-----------|--------|-----------|
| Founder premine | 0.2M KVNC | Genesis coinbase (P2PK) |
| Treasury | 10M KVNC | 10 × 1M RFC-005 vaults at genesis |
| Curve emission | 80M KVNC | Block subsidies |
| **MAX_SUPPLY** | **90.2M KVNC** | Enforced via `native_minted` |

Treasury tranche *k* (1..=10) unlocks at height `k * 31_536_000`.
Owner keys are **placeholders** (`TREASURY_SEED_BASE + k`) until ceremony.

---

## Coinbase maturity

| Parameter | Value |
|-----------|--------|
| `COINBASE_MATURITY` | **100** blocks |
| Error | `LedgerError::CoinbaseImmature` |

---

## Fees

| Parameter | Value |
|-----------|--------|
| Floor | `max(1, subsidy / 500_000)` atoms per byte |
| Producer share | **25%** (`fee / 4`) |
| Burned | **75%** |

---

## Supply metrics

| Metric | Definition |
|--------|------------|
| `total` / `native_minted` | cumulative minted |
| `circulating` | tip UTXO native total (approx.) |
| `burned` | cumulative 75% fee burn |
| `max_supply` | `MAX_SUPPLY` |

Exposed via `Ledger::supply()` and HTTP snapshot JSON fields.

---

## Consensus parameters (related)

| Parameter | Value |
|-----------|--------|
| GHOSTDAG **k** | 3 |
| PoW | real, opt-in |

---

## References

- `crates/kovanica-state/src/ledger.rs`
- `crates/kovanica-node/src/explorer.rs` — `NetworkProfile`
- RFC-005 `VaultScript`
