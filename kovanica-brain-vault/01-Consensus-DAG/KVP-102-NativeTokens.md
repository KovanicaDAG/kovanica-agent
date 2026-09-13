# KVP-102 — Native Multi-Asset Tokens

- **Status:** Shipped
- **Public name:** **KVP-102** (Kovanica Protocol standard)
- **Normative RFC:** [RFC-002 — Native Tokens](./RFC-002-NativeTokens.md)
- **Registry:** [KVP.md](./KVP.md)
- **Implementation:** `kovanica-state` (tx / utxo / ledger), `kovanica-node`, `kovanica-ffi`
- **Tests:** `crates/kovanica-state/tests/native_token_consensus.rs` (29 tests)

This document is the **public KVP-102 specification**: the token / multi-asset
standard for Kovanica. Wire formats, conservation rules, and activation gates are
defined in full in **RFC-002**. If this page and RFC-002 ever disagree, **RFC-002
wins** until both are updated in the same change.

---

## 1. What KVP-102 is

**KVP-102** defines how **non-native assets** coexist with the native currency
**KVNC** on the same BlockDAG UTXO ledger.

| Concept | KVP-102 rule |
|---------|----------------|
| Native coin | **KVNC** — `asset_id = None` on outputs |
| Custom asset | 32-byte **AssetId** (BLAKE3 digest) on the output |
| Model | One asset per output (simplified Cardano multi-asset) |
| Fees | Always in **KVNC** only |
| Mint (regular tx) | Forbidden — coinbase only |
| Burn | Allowed (output sum &lt; input sum for that asset) |

KVP-102 is **not** an EVM token interface. There is no per-asset contract and no
`transfer` / `approve` ABI. Assets are first-class ledger state.

---

## 2. AssetId

```
asset_id = BLAKE3(policy_id ‖ name)    # 32 bytes
```

- Type: 32-byte newtype (`AssetId` in `kovanica-state`).
- **Native** convenience id: all zeros (`AssetId::native()`), but on the wire
  native value uses **flag 0 / `None`**, not the zero id.
- Display: lowercase hex (64 characters).

See RFC-002 §2 for constructors and helpers.

---

## 3. Output encoding (wire)

Per output, after the 8-byte value and before the 33-byte owner:

```
value       (8 bytes, little-endian u64)
asset_flag  (1 byte): 0 = native KVNC, 1 = KVP-102 asset present
[asset_id]  (32 bytes, only if flag == 1)
owner       (33 bytes, versioned address)
```

Minimum output size: **42 bytes**. This is a **format bump** relative to
pre–RFC-002 chains (testnet reset at activation). Full detail: RFC-002 §3.

---

## 4. Conservation (consensus)

For each `Option<AssetId>` bucket in a **regular** transaction:

1. **No minting** — an asset that appears only in outputs is rejected
   (`AssetNotConserved`).
2. **No inflation** — `outputs[asset] > inputs[asset]` rejected.
3. **Burn allowed** — `outputs[asset] < inputs[asset]` destroys the difference
   (not a fee).
4. **Fee = native only** — `fee = native_in - native_out`; must be ≥ 0.
5. **Zero-value outputs** rejected for every asset.

**Coinbase** may mint any asset (initial distribution). The subsidy / fee limit
applies only to **native** coinbase outputs. See RFC-002 §4–§5.

---

## 5. Activation

KVP-102 is gated on **blue score**:

- Default: `NATIVE_TOKEN_ACTIVATION_SCORE = 0` (active from genesis).
- Pre-activation: non-native outputs and spends of non-native UTXOs rejected
  (`PreActivationNativeToken`).
- Coinbase minting is **not** activation-gated.

Configurable via `Ledger::set_native_token_activation_score`. RFC-002 §6.

---

## 6. Node, FFI, and HTTP surface

| Layer | KVP-102 support |
|-------|------------------|
| Node | `send_*_asset`, `prepare_transfer_asset`, `balance_of_asset` |
| FFI | `send_asset`, `send_from_asset`, `balance_of_asset`, `asset_id_hex` on history |
| Web | AssetPicker + explorer badges (HTTP utxos/history/prepare expose asset_id) |
| Checkpoint | UTXO set **v4** (asset flag + id) |

`balance(owner)` remains **native KVNC only**; use `balance_of_asset` for
KVP-102 units.

---

## 7. Comparison (informational)

| Standard | Chain model | Where value lives |
|----------|-------------|-------------------|
| ERC-20 / BEP-20 | Account + contract | Contract storage |
| **KVP-102** | UTXO BlockDAG | Output `value` + `asset_id` |

---

## 8. Future work (from RFC-002)

- Tag-convention **mint/burn authority** (policy-bound mint beyond coinbase).
- Optional richer multi-asset-per-output encoding (current: one asset per output).
- HTTP API: `asset_id` on `/api/utxos`, `/api/history`, `/api/prepare` (wire form `KVNC` or 64-hex).

---

## 9. References

- Normative: [RFC-002-NativeTokens.md](./RFC-002-NativeTokens.md)
- Registry: [KVP.md](./KVP.md)
- Related: [KVP-101 / RFC-001 Multisig](./RFC-001-Multisig.md),
  [KVP-103 / RFC-003 Stealth + script v2](./RFC-003-ScriptV2-and-Stealth.md)
