# RFC-002 — Native Tokens (Cardano Multi-Asset Model)

- **Status:** Shipped (implemented in `kovanica-state`)
- **Public standard name:** **[KVP-102](./KVP-102-NativeTokens.md)** (see [KVP registry](./KVP.md))
- **Reference implementation:** `crates/kovanica-state/src/tx.rs`,
  `crates/kovanica-state/src/utxo.rs`, `crates/kovanica-state/src/ledger.rs`,
  `crates/kovanica-node/src/node.rs`, `crates/kovanica-ffi/src/light_node.rs`
- **Consensus test suite:** `crates/kovanica-state/tests/native_token_consensus.rs` (29 tests)
- **Activation:** gated on blue score (see [Activation gating](#activation-gating))

This document is the **normative** specification that the native-token code in
`kovanica-state` references as "RFC-002". The public-facing standard name is
**KVP-102**. It describes the asset identifier format, the output encoding,
per-asset conservation, coinbase minting, and the consensus activation gate. It
is grounded in the shipped implementation — do not change the formats here
without changing the code, and vice versa.

---

## 1. Overview

A **native token** is a second asset class that coexists with the protocol's
native currency, **KVNC**, in the same UTXO ledger. The design follows the
Cardano multi-asset model: every output carries an optional **asset id**, and
`None` denotes the native KVNC asset. Value is conserved **per asset**, so a
transaction may move several distinct assets in a single spend without any
cross-asset exchange.

The original plan proposed a `Vec<Asset>` per output (multiple assets per
output, Cardano-style). The shipped implementation **simplifies this to a single
`Option<AssetId>` per output** — one asset per output, or native. This keeps the
output encoding compact (a single flag byte) and the conservation logic
straightforward, at the cost of requiring one output per asset when a
transaction moves several assets at once (see §3).

The upgrade is **additive**: native KVNC outputs are unchanged in meaning, and
the native asset remains the only asset that can pay fees or be minted by the
subsidy (see §4 and §5).

---

## 2. AssetId format

An asset is identified by a **32-byte BLAKE3 digest**:

```
asset_id = BLAKE3(policy_id ‖ name)      # 32 bytes
```

- `policy_id` — the 32-byte identifier of the issuing policy/authority.
- `name` — the asset's name within that policy.
- `asset_id` — the 32-byte BLAKE3 hash of the concatenation.

The type is a newtype over `[u8; 32]` in `crates/kovanica-state/src/tx.rs`:

```rust
pub struct AssetId([u8; 32]);
```

### 2.1 Construction & helpers

- `AssetId::from_bytes([u8; 32])` — construct from raw bytes (decoding / tests).
- `AssetId::as_bytes()` — the raw 32 bytes.
- `AssetId::native()` — the native KVNC asset id, **all zeros** (`[0u8; 32]`).
- `AssetId::is_native()` — whether this is the all-zero native id.
- `AssetId::to_hex()` / `Display` — lowercase hex rendering.

The native asset is canonically represented as `None` on an output (see §3); the
all-zero `AssetId::native()` exists as a convenience and is *not* the on-wire
representation of native value.

---

## 3. Output format & encoding

`TxOutput` gained an optional asset id:

```rust
pub struct TxOutput {
    pub value: u64,
    pub asset_id: Option<AssetId>,   // None = native KVNC
    pub owner: Address,
}
```

### 3.1 Constructors

- `TxOutput::new(value, asset_id: Option<AssetId>, owner)` — explicit asset id.
- `TxOutput::native(value, owner)` — native KVNC output (`asset_id = None`).

### 3.2 Canonical transaction encoding

The canonical transaction encoding writes, per output, **after the 8-byte value
and before the 33-byte owner address**, a **1-byte asset flag** followed by the
asset id when present:

```
value (8 bytes)
asset_flag (1 byte): 0 = native (None), 1 = asset present
[asset_id (32 bytes)]   # only when asset_flag == 1
owner (33 bytes)
```

- `asset_flag == 0` → native KVNC output (`asset_id = None`).
- `asset_flag == 1` → the next 32 bytes are the `AssetId`.

The **minimum output size is now 42 bytes** (8 value + 1 flag + 33 owner),
up from 41. The decoder's `read_count` bound for outputs uses this 42-byte
minimum.

### 3.3 Format bump (breaking)

Adding the asset flag byte changes the canonical encoding of **every**
transaction, including genesis. This is a **wire-format bump**:

- Old wire blobs / checkpoints are **undecodable** by the new code.
- The **genesis block id changes** (it is a hash of the encoded genesis
  coinbase).
- The **live testnet chain resets at activation** — see
  `crates/kovanica-ffi/tests/live_sync_spike.rs`, whose live-chain tests are
  `#[ignore]`d until the testnet is re-captured on the new chain.

---

## 4. Conservation rules

Conservation is enforced **per asset** in `apply_regular`
(`crates/kovanica-state/src/ledger.rs`). Inputs and outputs are grouped by
`Option<AssetId>`; for each asset the input sum and output sum are compared.

### 4.1 Per-asset conservation

For each asset id present in the transaction's inputs:

- **`out_val > in_val` is rejected** with `LedgerError::AssetNotConserved`
  (this would mint value).
- **`out_val < in_val` is allowed** — the difference is treated as **burned**
  (destroyed), not as a fee.

### 4.2 Minting is rejected

Any asset that appears **only in outputs** (no input of that asset) is rejected
with `LedgerError::AssetNotConserved` (`inputs: 0`). A regular transaction
cannot mint an asset — only a coinbase can (see §5).

### 4.3 Fee must be native

The transaction fee is the difference between native input and native output:

```
fee = native_in - native_out
```

- **`native_out > native_in` is rejected** with `LedgerError::AssetNotConserved`
  (`asset_id: None`) — the fee cannot be negative.
- Asset value is never counted toward the fee; burning an asset simply destroys
  it.

> **Note on error variants:** the `LedgerError::AssetMismatch` variant exists
> in the enum and is rendered by `Display`, but is **not constructed anywhere**
> in the shipped code. All conservation failures — including the native-fee
> check — use `LedgerError::AssetNotConserved`. `AssetMismatch` is currently
> dead code and should not be relied upon by callers.

### 4.4 Zero-value outputs

An output with `value == 0` is rejected (`LedgerError::ZeroValueOutput`),
regardless of asset.

---

## 5. Coinbase minting

`apply_coinbase` (`crates/kovanica-state/src/ledger.rs`) is the **only** path
that may mint an asset. A coinbase may create outputs of **any** asset id — this
is the initial-distribution path.

### 5.1 Subsidy limit applies to native only

The coinbase's subsidy/fee limit (`subsidy + fees`) applies **only to native
KVNC outputs**:

- Only outputs with `asset_id.is_none()` are summed into `claimed_native`.
- If `claimed_native > allowed`, the coinbase is rejected with
  `LedgerError::CoinbaseOverspend`.
- Asset outputs are **not** counted against the limit — a coinbase may mint
  arbitrary amounts of any asset alongside its native subsidy.

### 5.2 Coinbase is not activation-gated

The native-token activation gate does **not** apply to coinbase outputs. The
`_native_token_activation_score` parameter of `apply_coinbase` is unused; a
coinbase may mint assets even before activation (this is what makes initial
distribution possible). Only **regular** transactions are gated (see §6).

---

## 6. Activation gating

Native tokens are a **consensus upgrade** gated on **blue score** so that
pre-activation blocks cannot create or spend asset outputs.

- Default activation threshold: `NATIVE_TOKEN_ACTIVATION_SCORE = 0` (i.e.
  active from genesis by default).
- Configurable per ledger via `Ledger::set_native_token_activation_score(score)`;
  readable via `Ledger::native_token_activation_score()`.
- The gate is **inclusive**: a block is *pre-activation* when
  `blue_score <= activation_score`.

### 6.1 Pre-activation rules

While `blue_score <= native_token_activation_score`, the ledger rejects
(`LedgerError::PreActivationNativeToken`) in `apply_regular`:

- Any **output** whose `asset_id.is_some()` (a non-native asset output).
- Any **spend** of an output whose `asset_id.is_some()` (an asset input).

### 6.2 Post-activation

Once `blue_score > native_token_activation_score`:

- Asset outputs may be created and spent normally.
- Native KVNC outputs remain valid forever (the upgrade is additive).

### 6.3 Enforcement paths

The gate is threaded through `apply_block_inner`, which takes an explicit
`native_token_activation_score` parameter. It is enforced identically on both
the **incremental `Ledger`** path (`Ledger::insert`, which passes
`self.native_token_activation_score`) and the **batch** paths (`apply_block`,
`apply_block_with_stake`, and `apply_dag`, which pass the
`NATIVE_TOKEN_ACTIVATION_SCORE` constant). The checkpoint restore path also
re-initializes the ledger with the constant.

---

## 7. Node & FFI surface

### 7.1 Node layer (`crates/kovanica-node/src/node.rs`)

The node exposes asset-aware transfer and balance helpers. The transfer
helpers each have a native (`None`) counterpart that delegates to them:

- `send_asset(from_seed, amount, to_seed, asset_id)` — send from actor to actor.
- `send_to_asset(from_seed, amount, to, asset_id)` — send from actor to address.
- `send_with_asset(kp, amount, to, asset_id)` — send from an explicit keypair.
- `build_transfer_with_asset(kp, amount, to_addr, asset_id)` — build a signed
  transfer.
- `prepare_transfer_asset(from, amount, to, asset_id)` — build an **unsigned**
  transfer, selecting covering UTXOs of the given asset.
- `balance_of_asset(owner, asset_id)` — per-asset spendable balance.

`Node::balance(owner)` counts **native KVNC only** (it filters on
`asset_id.is_none()`); asset balances require `balance_of_asset`.

### 7.2 FFI layer (`crates/kovanica-ffi/src/light_node.rs`)

The mobile FFI exposes:

- `send_asset(from_seed, amount, to_seed, asset_id_hex)` — `asset_id_hex` is the
  32-byte asset id as lowercase hex; `None` = native KVNC.
- `send_from_asset(signing_secret_hex, amount, to_address, asset_id_hex)` — send
  using an imported secret.
- `balance_of_asset(address, asset_id_hex)` — per-asset balance as a decimal
  string.

The FFI records gained an optional asset id:

- `HistoryEntry.asset_id_hex: Option<String>` — asset id (lowercase hex) of a
  history event; `None` = native KVNC.
- `MultisigSpendOutput.asset_id_hex: Option<String>` — asset id of a multisig
  spend output; `None` = native KVNC.

---

## 8. Persistence

### 8.1 UTXO set encoding (v4)

`UtxoSet::encode` / `UtxoSet::decode` (`crates/kovanica-state/src/utxo.rs`) were
bumped to **v4**: each entry now writes the asset flag byte (0 = native, 1 =
present) followed by 32 asset bytes when present, after the owner address. This
is the encoding used inside checkpoints.

### 8.2 Checkpoint format (v4)

`CHECKPOINT_VERSION` in `crates/kovanica-state/src/ledger.rs` is **4**. v4 adds
the optional `asset_id` to the embedded UTXO-set encoding. The reader accepts
versions `3..=4` (v3 = stake registry, v4 = asset_id in UTXO).

### 8.3 Snapshot format

The ledger snapshot (`LEDGER_VERSION = 2`) and the underlying DAG snapshot
(`VERSION = 5` in `crates/kovanica-dag/src/snapshot.rs`) were **not** bumped for
assets. A snapshot stores the replay log of blocks, not per-output state; on
load the blocks are replayed through the new transaction encoding (which carries
the asset flag), so asset outputs round-trip without a format change. Only the
checkpoint — which stores the materialized UTXO set directly — required a bump.

---

## 9. Future work

### 9.1 Mint/burn authority via tag convention

The plan's original design called for mint/burn authority via a **tag
convention** (the `KVB1` / `KVU1`-style tags used by the stake registry in
`stake.rs`): a transaction carrying a designated tag would be authorized to mint
or burn a specific asset. **This is not yet implemented.**

In the shipped code:

- **Minting** is coinbase-only (see §5). A regular transaction that creates an
  asset with no corresponding input is rejected.
- **Burning** is unrestricted — any transaction may destroy asset value by
  producing fewer asset outputs than inputs (see §4.1).
- There is **no tag-based authority** to mint or burn on behalf of a policy.

Tag-convention mint/burn authority is left as future work.

---

## 10. Test coverage summary

`crates/kovanica-state/tests/native_token_consensus.rs` (29 tests) covers:

1. **Positive single/multi-asset transfers** — single-asset transfer,
   multi-asset transfer in one transaction, mixed native + asset transfer.
2. **Invalid asset ids** — unknown asset (no input of that asset), asset-id
   mismatch (spend asset A, output asset B).
3. **Per-asset conservation** — inflation rejected, exact-match conservation,
   fee-in-native, asset burning allowed, multiple assets conserved
   independently.
4. **Native-only coinbase + fee-in-native** — coinbase may mint any asset,
   native coinbase, mixed coinbase, fee must be native.
5. **Activation gating** — pre-activation output rejected, pre-activation spend
   rejected, post-activation output/spend allowed, exact boundary transition.
6. **Mixed native/asset blocks + parallel DAG conflicts** — mixed block,
   parallel DAG double-spend resolution by linearization, `apply_dag` with
   assets.
7. **Checkpoint/snapshot roundtrip with asset_id** — checkpoint roundtrip and
   snapshot roundtrip both preserve per-asset balances.
8. **Edge cases** — zero-value asset output rejected, asset id is 32 bytes,
   native asset id is zeros, custom asset id not native, `TxOutput::native` /
   `TxOutput::new` constructors.

---

## 11. Wire & persistence notes

- Asset ids are ordinary 32-byte digests on the wire; no separate address type
  exists — an asset output is locked to the same 33-byte versioned `Address` as
  a native output.
- Asset transactions serialize through the existing canonical transaction
  encoding (with the added flag byte) and survive snapshot/checkpoint replay
  unchanged.
- The format bump (§3.3) means pre-RFC-002 wire blobs and checkpoints are
  undecodable, and the live testnet chain resets at activation.
