# RFC-005 — Time-Lock Vault / Escrow (5.2)

- **Status:** **Shipped** — implemented on `consensus/vault-rfc-005-csv`
  (checkpoint commit `a470268`); state/node/test suites green, draft PR open
- **Reference implementation:** `crates/kovanica-state/src/vault.rs`,
  `crates/kovanica-state/src/utxo.rs` (creation-height, UTXO v6),
  `crates/kovanica-state/src/ledger.rs` (CSV rule + vault gates, checkpoint v6),
  `crates/kovanica-state/src/script_v2.rs` (CSV doc points at the ledger rule),
  `crates/kovanica-node/src/node.rs` + `rpc.rs` (vault helpers + RPC commands)
- **Consensus test suite:** `crates/kovanica-state/tests/vault.rs` (26 tests),
  `crates/kovanica-node/tests/vault_node.rs` (5 tests)
- **Activation:** gated on blue score (mirrors RFC-001/002/003/004 `*_ACTIVATION_SCORE`)
- **Format bump:** **checkpoint v6** (UTXO entries gain a creation-height field);
  snapshot format and wire tx encoding are **unchanged**
- **Reference protocols:** Bitcoin BIP-68 (relative lock-time), BIP-112 (CSV),
  BIP-65 (CLTV), BIP-113 (locktime semantics adapted to block height),
  RFC-004 (HTLC template + real CLTV enforcement), RFC-003 (script v2 CSV opcode,
  tx-level `sequence`), RFC-001 (versioned-hash template pattern)

This document is the specification for the **time-lock vault / escrow** slice
(5.2 on the `2026-09-05` evolving plan). It does two things in **one consensus
change**:

1. **Makes CSV real** — BIP-68/BIP-112 relative locktime, the deferred half of
   RFC-004's §5.2. Requires **per-UTXO creation-height tracking** the ledger does
   not store today.
2. **Adds a dedicated time-lock vault template** (`0x05` address) that uses CSV
   and CLTV to lock value until a block height and/or a relative age, for escrow,
   inheritance timers, and locked savings — the `tests/vault.rs` slice of the
   plan.

---

## 1. Overview

RFC-004 shipped CLTV (BIP-65/BIP-113) with real enforcement: a transaction whose
`n_lock_time` is above the spending block's height is rejected
(`NonFinalTransaction`), so a `CHECKLOCKTIMEVERIFY v` inside a script v2 program
actually constrains spends to `block_height >= n_lock_time >= v`.

CSV (BIP-68/BIP-112 relative locktime) was **explicitly deferred** because it is
not expressible with the current state: relative locktime measures the time since
the *confirming block of the output being spent*, i.e. each input is unlocked when
`block_height >= creation_height(input_utxo) + sequence(input)`. The ledger never
records when a UTXO entered the set, so `tx.sequence` today is only checked
*decoratively* inside script v2 (`SEQUENCE >= v` against the raw field).

**RFC-005 closes that gap** and layers a vault template on top.

### 1.1 Design shape

| Piece | What changes |
|---|---|
| `UtxoSet` entries | `HashMap<OutPoint, (TxOutput, /*creation_height*/ u64)>` — every unspent output remembers the linearized block height it was created at. |
| Ledger `apply_block`/`apply_dag` | When a transaction is applied, new outputs are recorded with `creation_height = block_height`; spends look up the stored height, not `0`. |
| Finality pruning | Per-block state is already pruned at finality; creation-height metadata lives inside the **merged** UTXO view so pruning is unaffected (a pruned-out UTXO is gone from the merged set; a surviving UTXO keeps its stored height). |
| Checkpoint/`UtxoSet::encode` | Bump to **v6**: each entry gains an 8-byte `creation_height` after the output payload. Old checkpoints decode with `creation_height = 0` (pre-upgrade UTXOs are unlocked immediately — safe because CSV only *delays* spends, never fast-forwards them). |
| `Transaction.sequence` | Unchanged on the wire (RFC-003 field); CSV now has **real** meaning: `sequence != 0` is a relative block lock measured per input from that input's UTXO creation height. |
| Script v2 CSV opcode | The opcode drops the decorative `SEQUENCE >= v` check only in favor of ledger-level real enforcement (see §3.3). |
| Vault template | New `0x05` address, `VaultScript`, two spend paths (matured / unlocked-by-CSV-or-CLVT) — see §4. |

### 1.2 Reference protocols

- **BIP-68**: relative lock-time via `sequence`; a non-final input is one whose
  relative lock has not elapsed; an input with `sequence == 0` is final
  immediately (no relative constraint). We use the **block-count** interpretation
  only (`nSequence` `0x00400000` disable-flag semantics adapted: see §3.1), never
  the time-based unit, because the ledger's only consensus clock is block height.
- **BIP-112** (`CHECKSEQUENCEVERIFY`): fails if the evaluated relative lock-time
  has not yet passed (relative to the input's UTXO age, in this adaptation).
- **BIP-65** (`CHECKLOCKTIMEVERIFY`), **BIP-113**: absolute height semantics —
  already real from RFC-004; the vault reuses them unchanged.
- **RFC-004 §5.2** is the normative deferral this RFC discharges.

---

## 2. Decision — a dedicated `0x05` vault template, plus a consensus-enforced CSV

As with RFC-004's HTLC, the vault is **not** an extension of script v2. It is a
dedicated, structurally-validated template with its own address version `0x05`,
following the RFC-001/004 pattern: versioned address =
`0x05 || BLAKE3(template_bytes)`, template validated at parse, ledger branches on
owner version.

The CSV half, by contrast, is **not** opt-in per-template: it is a ledger-level
transaction-finality rule (like the RFC-004 CLTV fix), because `sequence` lives on
`Transaction`, applies to *every* input of a tx, and must be enforced by the same
`NonFinalTransaction`-style gate that makes CLTV real. The two pieces compose:
a vault template's CSV requirement constrains its own spend transaction, and the
ledger enforces that transaction's `sequence` against the vault output's
creation height.

### 2.1 Why the ledger gate, not just the script opcode

The decorative check `SEQUENCE >= v` in script v2 proves only "the spend
transaction declared a `sequence` ≥ `v`". It says nothing about **time elapsed
since the vault output was created**, because that age is not recorded. Real CSV
needs the creation height *at input resolution*, which only the ledger knows. So
CSV finality becomes a ledger rule:

> If a transaction spending UTXO `u` has `sequence(u) = s != 0`, the spend is
> non-final while `block_height < creation_height(u) + s`.

This is applied in the same pass as the existing CLTV
(`apply_regular` → `LedgerError::NonFinalTransaction` generalized to carry a
relative cause), and it is what makes the script-v2 CSV opcode meaningful in
vault programs too.

---

## 3. CSV: relative locktime with per-UTXO creation height

### 3.1 Encoding and semantics

- `sequence` is a `u32` already on `Transaction` (RFC-003) and is part of the
  sighash domain (RFC-004 CLTV work) — **no wire change**.
- `sequence == 0`: the input is final; no relative lock (backwards compatible —
  every existing transaction has `sequence == 0` and behaves exactly as before).
- `sequence == 0xFFFFFFFF`: also final (BIP-68 treats max sequence as "no
  relative lock"); accepted and treated as `0`.
- `1 <= sequence < 0x80000000`: the input is non-final until
  `block_height >= creation_height(input_utxo) + sequence` blocks of relative
  age. The top bit (`0x80000000`) is the BIP-68 **disable-flag**: when set, the
  field is ignored (final) — keeping the flag reserved for forward-compat.
- The relative age is measured in **blocks of linearized height**, matching the
  CLTV clock (`height == blue_score` for every block; see RFC-004 §6 "DAG-vs-chain
  locktime semantics"). This is the BIP-113 adaptation already applied to CLTV,
  applied again to CSV: height is the only unambiguous consensus clock.

### 3.2 State: creation height in the UTXO set

`UtxoSet` becomes `HashMap<OutPoint, UtxoEntry>` where

```rust
struct UtxoEntry {
    output: TxOutput,
    /// Linearized block height at which this output entered the UTXO set.
    creation_height: u64,
}
```

- **Write path.** `apply_block` inserts outputs with `creation_height =
  block_height` of the applying block (its blue score).
- **Read path.** Input resolution reads the entry's `creation_height` (was
  `TxOutput` directly; all existing call sites that want the output now read
  `entry.output`).
- **Checkpoint.** `UtxoSet::encode`/`decode` bump to **v6**: after each output
  payload, 8-byte LE `creation_height`. Decode of v5 (and earlier) data — the
  active testnet's checkpoints — treats `creation_height = 0` (all pre-upgrade
  UTXOs are immediately spendable; CSV only *delays*, never re-enables, so this is
  the safe default). The `encoded_len` computation gains the 8 bytes.
- **Snapshots / replay.** Snapshot format is unchanged (block records already
  carry block ids; the ledger recomputes per-block UTXO state from scratch on
  replay, so creation heights derive from the replay itself). Only the
  **checkpoint** (merged-state) encoding needs the field.
- **Pruning.** Finality pruning discards per-block state, including the creation-
  height metadata of pruned *blocks*; surviving merged-state UTXOs retain their
  stored creation height. `with_finality` is orthogonal.

### 3.3 Script v2 CSV opcode

The opcode remains, but its meaning is now "this program requires the relative
lock of its input to have elapsed **as enforced by the ledger**." The program's
runtime check is still `SEQUENCE >= v` (the spend declares a sequence at least
`v`); the *age* part is enforced at transaction level in `apply_regular`. A
spender cannot bypass: any vault spend that declares a too-small `sequence` fails
the script; any spend whose declared `sequence` has not yet aged to the current
height fails the ledger. Together: effective constraint
`block_height >= creation_height(out) + seq >= creation_height(out) + v` — the
BIP-68/BIP-112 composition.

### 3.4 Error surface

`LedgerError::NonFinalTransaction` gains a second shape (or a sibling variant):

```rust
NonFinalRelativeSequence {
    tx: TxId,
    outpoint: OutPoint,
    creation_height: u64,
    sequence: u32,
    block_height: u64,
}
```

Distinct from the existing absolute `NonFinalTransaction` so adversarial tests
and RPC errors can tell CLTV-declined from CSV-declined spends apart.

---

## 4. The vault template (`0x05`)

### 4.1 Template (`VaultScript`)

>> Encoding note: the exact byte layout below is the *design commitment*; the
>> implementation must match it exactly once the RFC is approved (do not mutate
>> this section without a spec amendment).

```
VaultScript (40 bytes):
  unlock_height (4B LE)      — absolute block height (CLTV-style) after which the
                               vault may be spent; 0 = no absolute lock
  csv (4B LE)                — relative blocks since this output's creation after
                               which it may be spent (0 = no relative lock)
  owner_pk (32B)             — the Ed25519 public key authorised to spend when
                               unlocked
Address = 0x05 || BLAKE3(template)
```

Semantics: the vault is spendable as soon as *both* locks have elapsed —
`block_height >= unlock_height` **and** `block_height >= creation_height + csv`.
`unlock_height = 0` and `csv = 0` (both "no lock") is invalid at parse: a vault
with no lock is just a P2PK output and must be created as such (prevents
an address-collision footgun where several scripts hash to the same address).

`VaultScript::new` validates: `unlock_height` and `csv` are plain `u32` (no
disable-flag bits allowed in the template); `owner_pk` is a valid Ed25519 point.

### 4.2 Spend paths

Witness vector on a `0x05` input:

- `witness[0]`: raw 40-byte template (BLAKE3 must match the owner hash).
- `witness[1]`: 64-byte Ed25519 signature by `owner_pk` over the transaction
  sighash (same domain as RFC-004 §Redeem/Refund: BLAKE3 of the witness-free
  encoding).

Spend validation order (all requirements, not an OR):

1. Script-hash match: `BLAKE3(witness[0]) == owner.hash`; template parse strict.
2. Signature: `witness.len() == 2`; `verify(owner_pk, sighash_commitment, witness[1])`.
3. Absolute lock: `block_height >= unlock_height` (ledger position of the
   spending tx's block).
4. Relative lock: `block_height >= creation_height + csv` (creation height from
   the UTXO entry, via §3).

A spend of a locked vault fails with a dedicated error
(`LedgerError::VaultAbsoluteNotReached { tx, required, block_height }` /
`LedgerError::VaultRelativeNotReached { tx, outpoint, required, creation_height, block_height }`),
distinct from the generic finality error so node RPC/FFI can render intent.

Rationale for both-locks-required (not either): a *time-lock vault* is
unconditionally locked until both clocks pass; an escrow that wants
"height X, whichever first" is expressible by setting one lock to 0. This is the
conservative reading of §5.2 and the simplest to reason about adversarially.

### 4.3 Activation gating

`VAULT_ACTIVATION_SCORE` (default 0, mirroring RFC-004 `HTLC_ACTIVATION_SCORE`):
before `blue_score > VAULT_ACTIVATION_SCORE` the ledger rejects
`0x05` outputs and `0x05` spends (`PreActivationVault`). Post-activation, P2PK
(etc.) paths are unchanged forever. Enforced identically in the incremental
`Ledger` and batch `apply_dag`/`apply_block` paths.

The CSV ledger rule (§3) is **not** gated behind the vault activation: it is a
transaction-finality rule (like RFC-004's CLTV fix) and applies from the zero
height, because any pre-upgrade `sequence = 0` tx is final and unaffected, and
any *new* tx declaring `sequence != 0` is a deliberate opt-in to relative
locking. This keeps the wire/checkpoint upgrade neutral for existing spends.

---

## 5. Implementation lanes (all landed except FFI; works in one feature branch)

| Lane | Files | Notes | Status |
|---|---|---|---|
| L1 State: creation-height | `utxo.rs` | `UtxoEntry { output, creation_height }`; `UtxoSet` API returns the entry; `encode`/`decode` → v6; `encoded_len`. | ✅ |
| L2 Ledger: CSV + vault | `ledger.rs` | insert outputs with applying block's height; resolve `sequence` per input against entry creation height; `0x05` branch in the owner-version match with validation §4.2. | ✅ |
| L3 Template | `vault.rs` (new) | `VaultScript`, parse, address, `VAULT_ACTIVATION_SCORE`. | ✅ |
| L4 Script doc fix | `script_v2.rs` | CSV opcode doc now points at RFC-005 (ledger-enforced relative lock). | ✅ |
| L5 Node/RPC/FFI | `node.rs`, `rpc.rs`, `light_node.rs` | `create_vault`/`release_vault`/`balance_of_vault`, `vault_create`/`vault_release`/`vault_balance` RPC commands. **FFI passthrough deferred** (HTLC slice is the model). | ✅ node/RPC; ⏳ FFI |
| L6 Tests | `tests/vault.rs` (26), `tests/vault_node.rs` (5) | §6 suite. | ✅ |
| L7 Docs | `AGENTS.md`, `KVP.md` (KVP-105), this RFC, plan file | same change as L1–L6. | ✅ |

`cargo fmt --check`, `cargo clippy --all-targets`, `cargo test` (full workspace),
then a draft PR gated green. Feature branch: `consensus/vault-rfc-005-csv`.

---

## 6. Test suite (landed; deterministic + adversarial)

`crates/kovanica-state/tests/vault.rs` (26 tests) plus
`crates/kovanica-node/tests/vault_node.rs` (5), all through the incremental
`Ledger` and the batch `apply_dag` path:

- **CSV ledger rule**
  - `csv_zero_final` — `sequence = 0` is immediately final (regression).
  - `csv_disable_flag_final` — top-bit set → final regardless of low bits.
  - `csv_aged_unlocks` — output created at height `c`, tx with `sequence = 3`
    rejected at `c+2`, accepted at `c+3`.
  - `csv_parallel_utxo_lookup` — two inputs with different creation heights,
    each checked individually (one final, one not → reject).
  - `csv_roundtrip_checkpoint_v6` — checkpoint encodes entries with creation
    height; decode matches; v5 (old) checkpoint decodes with height 0.
  - `csv_cltv_compose` — tx with both `n_lock_time` and `sequence` rejected if
    either is not met.
- **Vault template**
  - `vault_locked_rejected` — both locks unreached.
  - `vault_absolute_unlock` — only `unlock_height` set; spend at target height.
  - `vault_relative_unlock` — only `csv` set; spend after relative age; rejected
    one block early.
  - `vault_both_locks_required` — either clock individually insufficient.
  - `vault_no_lock_invalid` — `unlock_height = 0, csv = 0` rejected at parse.
  - `vault_bad_script_hash` / `vault_bad_signature` / `vault_tampered_template`
    (flip each field byte → address mismatch).
  - `vault_pre_activation_rejected` — with `VAULT_ACTIVATION_SCORE` raised,
    `0x05` outputs/spends fail pre-gate, pass post-gate; P2PK unchanged.
  - `vault_parallel_dag_conflict` — two parallel blocks both spend the same
    vault output; each valid in its own view, merger rejects one (double-spend).
  - `vault_snapshot_roundtrip` — ledger save/load replays vault outputs with
    their creation heights intact.
- **Adversarial**
  - `csv_understate_sequence` — spender declares `sequence = 1` for an output
    that needs `v = 2` from a vault program → script rejects.
  - `csv_grind_creation` — adversary reorgs/blocks parallel-placed so that a
    UTXO's creation height appears earlier than it truly linearizes; assert the
    ledger rejects (creation height is a function of the DAG, `apply_dag`
    establishes the same metadata as the incremental path).
  - `vault_relay_replay` — a redeemed vault output cannot be re-spent (removed
    from the UTXO set on spend).

---

## 7. Open items / decisions required

- **CSV disable-flag** (`0x80000000`): confirm treating it as "final" is desired
  — alternative is to reject it as invalid (some BIP-68 implementations do).
  Current design: reserved-and-ignored (final), no wire change.
- **`sequence` granularity** (block count only vs. BIP-68's 9-bit/512-block
  time unit): this RFC uses **block count only** — the ledger has a block-height
  clock, not a median-time clock. State this is intentional.
- **Vault crypto**: only Ed25519 owner signatures; is a future multi-key
  (RFC-001) vault owner wanted before approval? (Would change the template to
  reference a script hash, not a raw pk.)
- **Exact error variants** and RPC/FFI surface names (the §4.2 names are
  proposals; implementation lanes will lock them, as RFC-004 did).
- Whether the vault slice also wants a **node-level escrow helper**
  (`create_vault`/`release_vault` orchestration) or purely the ledger template —
  the plan lists `tests/vault.rs` only; RFC-004 shipped both.

Resolved during implementation:

- **Disable flag** → kept as "final" (BIP-68's `0x00400000`-style disable, here
  the top bit): a final-declared input is trivially `>= v` for the script CSV
  opcode and skips the ledger relative gate.
- **Both-locks-required** → locked as specified (§4): both gates must elapse;
  equality (`>=`) is inclusive, so a release block exactly at
  `unlock_height`/`creation_height + csv` is valid.
- **Node escrow helper** → shipped: `create_vault`/`release_vault`/
  `balance_of_vault` + `vault_create`/`vault_release`/`vault_balance` RPC
  commands (RFC-004 parity).
- **Error variants** → `LedgerError::VaultAbsoluteNotReached` /
  `VaultRelativeNotReached` (struct variants: tx, outpoint, required, block
  height, and for relative the creation height) plus `NonFinalRelativeSequence`
  and `PreActivationVault`.
- **Chain-height clock** → the vault/CSV rules compare against the
  **selected-parent chain height**, not blue score (blue score counts merged
  blue blocks). `apply_dag` computes chain heights matching the incremental
  `Ledger`; guarded by `csv_grind_creation`.

---

## 8. Compatibility & migration

- **No wire-format bump**: `TxOutput.owner` stays 33 bytes; version `0x05` is new
  in existing space; tx encoding, sighash, snapshot (v5) unchanged. Old nodes
  reject `0x05` at parse (`VERSION_MAX` — needs a bump to allow `0x05`) — soft
  incompatibility handled by activation gating, same as RFC-004.
- **Checkpoint v6** strictly extends v5: all v5 bytes remain, new `creation_height`
  field appended per entry. Old readers (pre-upgrade nodes) reading a v6
  checkpoint will mis-parse — coordinate the bump with deployment, or gate node
  upgrade on the same release.
- **`VERSION_MAX`**: `keys.rs` currently caps address versions; adding `0x05`
  requires raising it. Objects with `0x05` are only decodable post-upgrade.
- **No testnet reset**: activation default `0`; existing UTXOs get
  `creation_height = 0` on v5→v6 checkpoint conversion, which is the safe
  immediate-unlock default.

---

## 9. Rationale summary (auditable)

- **Why a dedicated template, not script v2:** same commitment/structural-
  validation argument as RFC-004 §2 — script v2 has no immediate-data push and no
  `OP_IF/ELSE/ENDIF`, so a multi-path vault program is not faithfully expressible
  in the current opcode set; a versioned-hash template is the established
  pattern (RFC-001/003/004) and keeps the consensus branch list explicit.
- **Why ledger-level CSV (not opcode-only):** age-of-input is global state only
  the ledger has; opcode-only CSV is unenforceable (RFC-004 §5.2).
- **Why both locks required:** conservative reading of "vault / escrow"; each
  lock is optional (0 = off) so "first of" escrows can be expressed by using a
  single lock.
- **Why checkpoint v6 + snapshot unchanged:** snapshots are replay logs
  (creation heights recomputed); checkpoints are merged state (must carry the
  metadata). Mirrors how RFC-002/003 extended checkpoint v4/v5 without touching
  snapshot semantics.