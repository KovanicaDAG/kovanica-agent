# Kovanica Protocol Standards (KVP)

**KVP** (*Kovanica Protocol*) is the public numbering for consensus and ledger
standards on Kovanica. Each **KVP-N** maps 1:1 to an internal **RFC** document
that remains the normative engineering reference.

Numbering uses a **100 + RFC ordinal** scheme so public labels read closer to
familiar token-standard brands (e.g. ERC-20) while staying tied to the RFC series:

| KVP | RFC | Title | Status |
|-----|-----|-------|--------|
| **KVP-101** | [RFC-001](./RFC-001-Multisig.md) | Multisig (M-of-N P2SH) | Shipped |
| **KVP-102** | [RFC-002](./RFC-002-NativeTokens.md) | Native multi-asset tokens | Shipped |
| **KVP-103** | [RFC-003](./RFC-003-ScriptV2-and-Stealth.md) | Stealth addresses + script v2 | Shipped |
| **KVP-104** | [RFC-004](./RFC-004-Htlc.md) | HTLC atomic swaps | Shipped |
| **KVP-105** | [RFC-005](./RFC-005-Vault.md) | Time-lock vault / escrow (real CSV) | Shipped |

## Native coin vs token standard

- **KVNC** — native currency of the ledger (`asset_id = None` on outputs).
- **KVP-102** — the *standard* for non-native (and the rules governing all
  multi-asset outputs), not a second ticker.

> KVNC is native. Other assets are **KVP-102** assets under RFC-002.

## Documents

| Public standard | Normative RFC | Notes |
|-----------------|---------------|-------|
| [KVP-102](./KVP-102-NativeTokens.md) | [RFC-002](./RFC-002-NativeTokens.md) | Token / multi-asset standard |

Additional **KVP-10x** overview pages may be added for 101 / 103 / 104; until
then the RFC file is the full specification.

## Compatibility note

KVP-102 is **not** an ERC-20 (or BEP-20) contract interface. Value lives in the
UTXO set with an optional 32-byte `asset_id`. Fees are always paid in **KVNC**.
