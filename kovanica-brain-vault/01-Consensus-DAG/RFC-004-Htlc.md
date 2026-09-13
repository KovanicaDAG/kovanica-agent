# RFC-004 — HTLC / Atomic Swap (5.1)

- **Status:** **Shipped** (merged to `main` via PR #88, `fb13741`, 2026-09-08)
- **Reference implementation:** `crates/kovanica-state/src/htlc.rs`, `crates/kovanica-state/src/keys.rs`,
  `crates/kovanica-state/src/ledger.rs`, `crates/kovanica-node/src/atomic_swap.rs`,
  `crates/kovanica-node/src/node.rs`, `crates/kovanica-node/src/rpc.rs`,
  `crates/kovanica-ffi/src/light_node.rs`
- **Consensus test suite:** `crates/kovanica-state/tests/htlc.rs` (~23 tests)
- **Node tests:** `crates/kovanica-node/tests/htlc_node.rs` (~4 tests)
- **FFI tests:** `crates/kovanica-ffi/tests/ffi.rs` (`htlc_over_ffi`, `swap_session_over_ffi`)
- **Activation:** gated on blue score (see [Activation gating](#41-activation-gating))
- **Format bump:** **none** — no testnet reset (see [Wire & persistence notes](#11-wire--persistence-notes))

This document is the specification that the HTLC and atomic-swap code in
`kovanica-state` / `kovanica-node` references as "RFC-004". It describes the
`v0x04` HTLC address format, the 100-byte HTLC template, the two consensus
spend paths (redeem / refund), the companion CLTV enforcement fix, and the
Tier-Nolan atomic-swap orchestration layer. The design is locked; the
implementation lanes are dispatched and must match this spec — do not change
the formats here without changing the code, and vice versa.

**Reference protocols:** Bitcoin HTLC (BIP-199), Tier Nolan atomic swap,
Lightning Network (preimage revelation), BIP-65 (CLTV), BIP-113 (median-time-past
locktime semantics, adapted to block height), RFC-001 (multisig template
pattern), RFC-002 (per-asset conservation), RFC-003 (script v2 hash-lock +
timelock primitives). BIP-68/BIP-112 (relative locktime / CSV) is **deferred**
to the 5.2 vault — see [CSV deferred](#52-csv-deferred).

---

## 1. Overview

This RFC ships **one consensus upgrade** — HTLC / atomic swap (slice 5.1) —
plus a **companion consensus fix** that makes script v2's CLTV opcode real
(BIP-65/BIP-113). The two are separable commits; the HTLC template does not
depend on the CLTV fix, but the fix is required for HTLC refunds to be
meaningful on-chain (see §5).

An **HTLC** (hash time-locked contract) locks value behind a preimage hash and
a timeout: the **recipient** can redeem by revealing the preimage (proving
knowledge of a secret), and the **sender** can refund after the timeout. Two
HTLCs with the same preimage hash and **ordered timeouts** compose into a
**Tier Nolan atomic swap**: neither party can cheat because the preimage that
redeems one contract is revealed on-chain and immediately redeems the other.

The design follows the RFC-001 multisig pattern: a **dedicated, structurally
validated template** with a **new address version `0x04`**, rather than an
extension of script v2. The template commits to all four HTLC parameters
(preimage hash, recipient pk, sender pk, timeout) via the script hash; the
ledger enforces the two spend paths directly, with no script interpreter in the
consensus path.

**Design rationale (dedicated template, not script v2):** two gaps in the
current code force a dedicated template — see [§2](#2-decision--a-dedicated-0x04-template-not-a-script-v2-extension).

---

## 2. Decision — a dedicated `0x04` template, not a script v2 extension

HTLC is **not** expressed as a script-v2 program. It is a dedicated 100-byte
template with its own address version `0x04`, validated at parse time and
enforced directly by the ledger. This follows the RFC-001 multisig pattern:
versioned address = `version || BLAKE3(template_bytes)`, template validated at
parse, ledger branches on owner version.

Two gaps in the current code force this design:

### 2.1 Commitment gap

Script v2 has **no immediate-data push** and **no `OP_IF/ELSE/ENDIF`**, so it
cannot commit to a hash, two pubkeys, and a timeout *in the script*. The
existing hash-lock test puts the expected hash in the **witness**; the script
hash commits to nothing. A script-v2 HTLC would therefore commit only to the
program's opcode sequence, not to the contract parameters — anyone could spend
with a different preimage hash or timeout. The dedicated template commits to
all four parameters via `BLAKE3(template_bytes)`.

### 2.2 Time-enforcement gap

Script v2's CLTV/CSV are **decorative**: `CLTV` checks `tx.n_lock_time >= v`
but **nothing checks the block's actual height**. A spender can bypass any CLTV
by declaring `n_lock_time = 4_000_000_000`. The companion fix (§5) closes this
gap for CLTV; the HTLC refund path additionally enforces the timeout against
the **block's height** directly in the ledger, independent of the script
interpreter.

### 2.3 Why not reuse version `0x02`?

The owner version byte is the discriminator. Under `0x02` the ledger would have
to distinguish an HTLC template from a script-v2 program by content — a
coincidental 100-byte parse would misclassify. A dedicated version keeps the
branch unambiguous: `is_htlc()` is a single byte check, and a script-v2 spend
of an HTLC output (or vice versa) fails deterministically (test
`htlc_cross_version_confusion`).

---

## 3. HTLC representation

### 3.1 Template (`HtlcScript`, 100 bytes)

```
offset  size  field
0       32    preimage_hash   — BLAKE3(preimage), 32 bytes
32      32    recipient_pk    — Ed25519 public key, 32 bytes
64      32    sender_pk       — Ed25519 public key, 32 bytes
96      4     timeout         — u32 LE, absolute block height
```

- **No version byte inside the template** — the address version (`0x04`) is the
  discriminator.
- `preimage_hash` — BLAKE3 of the preimage; any 32 bytes accepted.
- `recipient_pk` / `sender_pk` — Ed25519 public keys; must be valid points and
  distinct from each other.
- `timeout` — u32 little-endian, **absolute block height** (not a duration).
  `0` = immediately refundable. `u32::MAX` = effectively never refundable on
  any reachable chain (test `htlc_timeout_overflow`).

### 3.2 Address version `0x04`

```rust
Address::VERSION_HTLC = 0x04
Address::htlc(script_hash)          // 0x04 || BLAKE3(template_bytes), 33 bytes
Address::from_htlc_script(script)   // htlc(BLAKE3(script))
Address::is_htlc()
VERSION_MAX bumps 0x03 → 0x04
```

- Same shape as P2SH (`0x01`) and script v2 (`0x02`): a 32-byte BLAKE3 digest
  of the template, not the template itself. The template is revealed at spend
  time in the witness (§4.3).
- Rendering unchanged: `kvnc…dag` (base58 over the 33 bytes), indistinguishable
  in shape from every other address; `Address::parse` accepts 66-hex or
  `kvnc…dag`.
- `VERSION_MAX` bump means old nodes reject version `0x04` at parse
  (`VERSION_MAX`) — a soft incompatibility handled by activation gating
  (§4.1). The `version_max_is_stealth` unit test in `keys.rs` is updated to
  the new max.

### 3.3 Parse-time validation (`HtlcScript::new` / `parse`)

Reject if:

- length ≠ 100 → `WrongLength`
- `recipient_pk` not a valid Ed25519 point → `InvalidRecipientKey`
- `sender_pk` not a valid Ed25519 point → `InvalidSenderKey`
- `recipient_pk == sender_pk` → `DuplicateKeys` (mirrors the RFC-001 multisig
  duplicate rule)

`preimage_hash`: any 32 bytes accepted. `timeout`: any u32 accepted.

---

## 4. Consensus rules

### 4.1 Activation gating

- `HTLC_ACTIVATION_SCORE: u64 = 0` (default) — active from genesis by default,
  consistent with RFC-001/002/003.
- Configurable via `Ledger::set_htlc_activation_score(score)`; readable via
  `Ledger::htlc_activation_score()`.
- The gate is **inclusive**: a block is *pre-activation* when
  `blue_score <= htlc_activation_score`.

**Pre-activation rules** (while `blue_score <= HTLC_ACTIVATION_SCORE`): the
ledger rejects (`PreActivationHtlc { tx, blue_score, activation_score }`) in
`apply_regular`:

- Any **output** whose `owner.is_htlc()` (a `v0x04` output).
- Any **spend** of a `v0x04` output (an HTLC input).

**Post-activation:** once `blue_score > HTLC_ACTIVATION_SCORE`, HTLC outputs
may be created and spent normally. P2PK/P2SH/script-v2/stealth outputs remain
valid forever.

**Enforcement paths:** threaded through `apply_block_inner`/`apply_regular` on
both the incremental `Ledger` path and the batch `apply_dag`/`apply_block`
paths. **Coinbase outputs are exempt** — the coinbase path bypasses
`apply_regular`, so a coinbase may mint an HTLC output pre-activation (same
rule as RFC-002/003).

### 4.2 Conservation

HTLC outputs are ordinary `TxOutput::new(value, asset_id, Address::htlc(...))`
— the owner is just a versioned address. **Per-asset conservation is
owner-agnostic** (RFC-002 §4): inputs and outputs are grouped by
`Option<AssetId>`; `out_val > in_val` is rejected (`AssetNotConserved`),
`out_val < in_val` is allowed (burned), any asset appearing only in outputs is
rejected, fees are paid in native KVNC only, zero-value outputs are rejected.
**No new conservation rules.**

### 4.3 Spend authorization — the two paths

The ledger branches in `apply_regular`:

```rust
else if prev.owner.is_htlc() { ... }   // after the script-v2 branch
```

```
witness[0] = template bytes
1. witness non-empty                          else InvalidWitnessCount { expected: 2, actual: 0 }
2. BLAKE3(witness[0]) == owner.payload()      else ScriptHashMismatch
3. HtlcScript::parse(witness[0])              else InvalidRedeemScript { reason }
4. branch on witness.len():
   3  → REDEEM:  witness[1] = preimage (any length), witness[2] = recipient sig (64B)
        a. sig.len() == 64                    else BadSignatureSize
        b. BLAKE3(preimage) == preimage_hash  else HtlcPreimageMismatch
        c. verify_pk(recipient_pk, sighash, sig)  else BadSignature
   2  → REFUND:  witness[1] = sender sig (64B)
        a. sig.len() == 64                    else BadSignatureSize
        b. height >= timeout                  else HtlcTimeoutNotReached { height, timeout }
        c. verify_pk(sender_pk, sighash, sig) else BadSignature
   n  → InvalidWitnessCount { expected: 2, actual: n }
```

- **Redeem has no time constraint** — BIP-199 puts the CLTV on the refund path
  only. A recipient may redeem after the timeout until the sender's refund is
  mined (test `htlc_redeem_after_timeout_allowed`).
- **Paths are mutually exclusive by witness length** — deterministic, no branch
  evaluation, no script interpreter in the consensus path.
- `verify_pk` (stealth's strict Ed25519 verifier against a raw 32-byte pubkey)
  is used rather than `verify` (P2PK-only, address-based).
- The timeout check uses the **block's height** (`height == blue_score` for
  every block — see §12), a pure function of the DAG, never wall-clock.

### 4.4 New `LedgerError` variants

```rust
PreActivationHtlc { tx: TxId, blue_score: u64, activation_score: u64 },
HtlcPreimageMismatch { tx: TxId, input: usize },
HtlcTimeoutNotReached { tx: TxId, input: usize, height: u64, timeout: u32 },
NonFinalTransaction { tx: TxId, n_lock_time: u32, height: u64 },
```

Reused from RFC-001/003: `ScriptHashMismatch`, `InvalidRedeemScript`,
`InvalidWitnessCount`, `BadSignatureSize`, `BadSignature`.

---

## 5. Companion consensus fix — CLTV becomes real (BIP-65/BIP-113)

### 5.1 The rule

In `apply_regular`, before the input loop:

```rust
// BIP-65/BIP-113: a transaction whose n_lock_time exceeds the block's height
// is non-final and cannot be mined.
if tx.n_lock_time() as u64 > height {
    return Err(NonFinalTransaction { tx: tx.id(), n_lock_time: tx.n_lock_time(), height });
}
```

Effective constraint: `block_height >= n_lock_time >= v` — Bitcoin's semantics
(BIP-65 absolute locktime; BIP-113's median-time-past is adapted here to the
block's own height, which is the DAG's unambiguous clock). A spender can no
longer bypass a CLTV by declaring `n_lock_time = 4_000_000_000` — such a
transaction is **non-final** and rejected at apply time.

- **Blast radius is tiny:** `n_lock_time` defaults to `0` in every constructor;
  only the two CLTV tests set it (updated to real semantics — see §10).
- **Consensus change** → own rationale + adversarial tests
  (`cltv_non_final_rejected`, `cltv_final_at_height`).
- **Separable commit.** The HTLC template does not depend on it; the fix is
  required for HTLC refunds to be meaningful (a refund tx with a locktime would
  otherwise be mineable before its own timeout).

### 5.2 CSV deferred

CSV (BIP-112) is **deferred to the 5.2 vault**. Relative locktime needs
**per-UTXO creation-height tracking**, which `UtxoSet` does not store. The
`sequence` field remains on `Transaction` (RFC-003) and CSV keeps its
decorative `tx.sequence >= v` check until the vault slice lands.

---

## 6. Atomic swap orchestration (`atomic_swap.rs`)

### 6.1 Protocol (Tier Nolan / BIP-199)

```
1. Alice generates preimage x, computes H = BLAKE3(x).
2. Alice funds HTLC-A:  H, recipient=Bob, sender=Alice, timeout=T_A, value=amount_a (asset_a).
3. Bob verifies HTLC-A on-chain (script hash, recipient=Bob, timeout=T_A).
4. Bob funds HTLC-B:    H, recipient=Alice, sender=Bob, timeout=T_B < T_A, value=amount_b (asset_b).
5. Alice redeems HTLC-B with x → gets asset_b; x revealed on-chain.
6. Bob extracts x from HTLC-B's redeem witness, redeems HTLC-A with x → gets asset_a.
7. Fallback: Bob refunds HTLC-B after T_B; Alice refunds HTLC-A after T_A.
```

This is the classic **Tier Nolan atomic swap** (BIP-199's HTLC building block):
the same preimage unlocks both contracts, and the timeout ordering guarantees
that whichever party redeems first cannot strand the other. The preimage
revelation is **trustless** — Bob does not need to ask Alice for `x`; he reads
it off the chain from HTLC-B's redeem witness (`extract_preimage`, §6.3).

### 6.2 Timeout ordering `T_B < T_A` — the safety invariant

`SwapSession::new` **enforces** `timeout_b < timeout_a` (`SwapError::TimeoutOrdering`).
The invariant is what makes the swap atomic:

- If Alice redeems HTLC-B at any time before `T_B`, Bob can extract `x` and
  redeem HTLC-A **before** `T_A` — he always has time.
- If Alice never redeems, Bob refunds HTLC-B after `T_B`, and Alice refunds
  HTLC-A after `T_A` — both get their funds back.

The margin `T_A − T_B` is **off-chain policy** (recommendation: ≥ 2× expected
block propagation latency). On a DAG, height advances on the **selected chain**,
so the margin must cover gossip + linearization lag, not just block time.

### 6.3 Module contents (pure library, no node dependency)

```rust
pub struct SwapParams {
    pub amount_a: u64,
    pub asset_a: Option<AssetId>,
    pub amount_b: u64,
    pub asset_b: Option<AssetId>,
    pub timeout_a: u32,   // HTLC-A refund height (absolute)
    pub timeout_b: u32,   // HTLC-B refund height; must be < timeout_a
}

pub enum SwapRole { Alice, Bob }

pub struct SwapSession {
    pub preimage: [u8; 32],
    pub preimage_hash: [u8; 32],
    pub htlc_a: HtlcScript,   // recipient = Bob, sender = Alice
    pub htlc_b: HtlcScript,   // recipient = Alice, sender = Bob
}

impl SwapSession {
    pub fn new(params: &SwapParams, alice_pk: [u8; 32], bob_pk: [u8; 32],
               preimage: [u8; 32]) -> Result<Self, SwapError>;
    // SwapError::TimeoutOrdering   (timeout_b >= timeout_a)
    // SwapError::SameParty         (alice_pk == bob_pk)
    pub fn verify_against(&self, script: &HtlcScript, role: SwapRole) -> bool;
    // Bob's on-chain verification of HTLC-A before funding HTLC-B.
}

pub fn generate_preimage() -> [u8; 32];          // OsRng; tests inject a fixed preimage
pub fn preimage_hash(preimage: &[u8]) -> [u8; 32];
pub fn extract_preimage(tx: &Transaction, script: &HtlcScript) -> Option<Vec<u8>>;
// Scans tx inputs for a redeem of `script` (witness.len()==3, witness[0]==script.bytes())
// and returns witness[1] — the trustless preimage-revelation path.
```

- `SwapSession::new` enforces both safety invariants: timeout ordering
  (`timeout_b < timeout_a`) and distinct parties (`alice_pk != bob_pk`).
- `verify_against` is Bob's on-chain check of HTLC-A (script hash, recipient,
  sender, timeout all match) **before** he funds HTLC-B — the step that makes
  the swap safe against a malicious Alice.
- `extract_preimage` is the trustless revelation path: Bob scans HTLC-B's
  redeem witness for the preimage without any off-chain communication.

---

## 7. Node API (`node.rs`)

Mirrors `send_to_script_v2` / `build_transfer_with_outputs`:

```rust
pub struct HtlcInfo {
    pub script: HtlcScript,
    pub address: Address,
    pub tx_id: TxId,
    pub outpoint: OutPoint,
}

pub fn create_htlc(&mut self, kp: &KeyPair, amount: u64, asset_id: Option<AssetId>,
                   recipient_pk: [u8; 32], preimage_hash: [u8; 32],
                   timeout: u32) -> Result<HtlcInfo, NodeError>;
// Builds TxOutput::new(amount, asset_id, Address::from_htlc_script(&script)),
// mines a block on the tips (same flow as send_to_script_v2).

pub fn redeem_htlc(&mut self, kp: &KeyPair, outpoint: OutPoint, script: &HtlcScript,
                   preimage: &[u8], to: Address) -> Result<TxId, NodeError>;
// Native: single input, witness [script, preimage, recipient_sig],
//         output = TxOutput::native(htlc_value - min_fee, to).
// Asset:  HTLC input (asset output to `to`) + a native fee input selected
//         largest-first from kp's UTXOs (mirrors build_transfer_with_asset).

pub fn refund_htlc(&mut self, kp: &KeyPair, outpoint: OutPoint, script: &HtlcScript,
                   to: Address) -> Result<TxId, NodeError>;
// Same shape, witness [script, sender_sig]. Fails with HtlcTimeoutNotReached
// until the chain reaches script.timeout().

pub fn balance_of_htlc(&self, script: &HtlcScript) -> u64;
pub fn scan_for_htlc_redeem(&self, script: &HtlcScript, from_height: u64)
    -> Option<(TxId, Vec<u8>)>;
// Linearizes from `from_height`, decodes payloads, runs extract_preimage —
// Bob's trustless discovery of Alice's redeem.
```

- `create_htlc` takes the **preimage hash** (not the preimage) — the sender
  never reveals the preimage at funding time.
- `redeem_htlc` / `refund_htlc` build the witness per §4.3 and submit as a new
  block on the tips.
- `scan_for_htlc_redeem` scans the linearized chain from `from_height` (the
  linearized order is the scan order) and returns the first redeem of `script`
  with its preimage — Bob's discovery path in the e2e swap.

---

## 8. RPC commands (`rpc.rs`, line commands)

```
htlc_create <from-seed> <amount> <recipient-pk-hex> <preimage-hash-hex> <timeout>
    → ok <tx-id> <script-hex> <address>
htlc_redeem <from-seed> <outpoint-tx-hex> <outpoint-index> <script-hex> <preimage-hex> <to-addr>
    → ok <tx-id>
htlc_refund <from-seed> <outpoint-tx-hex> <outpoint-index> <script-hex> <to-addr>
    → ok <tx-id>
htlc_balance <script-hex>
    → ok <balance>
```

---

## 9. FFI surface (`light_node.rs`)

```rust
pub struct HtlcInfo {
    pub script_hex: String,
    pub address: String,
    pub tx_id: String,
    pub outpoint_tx: String,
    pub outpoint_index: u32,
}
pub fn create_htlc(&self, signing_secret_hex: String, amount: u64,
                   asset_id_hex: Option<String>, recipient_pk_hex: String,
                   preimage_hash_hex: String, timeout: u32) -> Result<HtlcInfo, LightNodeError>;
pub fn redeem_htlc(&self, signing_secret_hex: String, outpoint_tx_hex: String,
                   outpoint_index: u32, script_hex: String, preimage_hex: String,
                   to_address: String) -> Result<String, LightNodeError>;
pub fn refund_htlc(&self, signing_secret_hex: String, outpoint_tx_hex: String,
                   outpoint_index: u32, script_hex: String,
                   to_address: String) -> Result<String, LightNodeError>;
pub fn balance_of_htlc(&self, script_hex: String) -> Result<u64, LightNodeError>;
pub fn htlc_script_hex(&self, preimage_hash_hex: String, recipient_pk_hex: String,
                       sender_pk_hex: String, timeout: u32) -> Result<String, LightNodeError>;
pub fn htlc_preimage_hash_hex(&self, preimage_hex: String) -> Result<String, LightNodeError>;
```

- `htlc_script_hex` / `htlc_preimage_hash_hex` are pure helpers so a mobile
  wallet can construct and inspect templates without a node round-trip.
- `asset_id_hex` is `Option<String>` — `None` = native KVNC (RFC-002).

---

## 10. Test coverage summary

Reference protocols named in the suite header: **BIP-199**, **Tier Nolan atomic
swap**, **Lightning**, **BIP-65/BIP-113**, **RFC-001/002/003**.

### 10.1 `crates/kovanica-state/tests/htlc.rs` (~23 tests)

| Test | Asserts |
|---|---|
| `htlc_redeem_happy_path` | correct preimage + recipient sig moves funds |
| `htlc_refund_happy_path` | chain advanced past timeout, sender refunds |
| `htlc_refund_before_timeout_rejected` | `HtlcTimeoutNotReached` |
| `htlc_refund_at_timeout_boundary` | `height == timeout` succeeds (`>=` semantics) |
| `htlc_wrong_preimage_rejected` | `HtlcPreimageMismatch` |
| `htlc_wrong_recipient_key_rejected` | redeem signed by sender → `BadSignature` |
| `htlc_refund_wrong_key_rejected` | refund signed by recipient → `BadSignature` |
| `htlc_redeem_after_timeout_allowed` | BIP-199: redeem still valid post-timeout until refund |
| `htlc_script_hash_mismatch` | wrong `witness[0]` → `ScriptHashMismatch` |
| `htlc_malformed_script_rejected` | bad length / invalid pk / duplicate pks → `InvalidRedeemScript` |
| `htlc_witness_count_rejected` | 1 or 4 elements → `InvalidWitnessCount` |
| `htlc_parallel_double_spend` | parallel redeem + refund blocks both valid in own view; merger resolves deterministically |
| `htlc_activation_boundary` | pre / exact-boundary / post activation for outputs and spends |
| `htlc_checkpoint_roundtrip` | HTLC outputs + spends survive `write_checkpoint`/`read_checkpoint` |
| `htlc_snapshot_roundtrip` | same for `write_snapshot`/`read_snapshot` |
| `htlc_mixed_block` | HTLC + P2PK + P2SH + script v2 + stealth + native token in one block |
| `htlc_asset_swap` | asset HTLC redeem conserves the asset; fee in native |
| `htlc_duplicate_scripts` | two identical templates → distinct outputs, both spendable |
| `htlc_cross_version_confusion` | script-v2 spend of an HTLC output fails (version disambiguates) |
| `htlc_timeout_overflow` | `timeout = u32::MAX` → refund rejected at any reachable height |
| `htlc_determinism` | same DAG built twice → identical outcomes |
| `cltv_non_final_rejected` | `n_lock_time > block height` → `NonFinalTransaction` (companion fix) |
| `cltv_final_at_height` | `n_lock_time == block height` → OK |

**Updated:** `stealth_script_v2_consensus.rs` CLTV tests move to real semantics
(`n_lock_time = 1`, `v = 1` pass; `n_lock_time = 1`, `v = 2` fail). CSV tests
unchanged (deferred to 5.2).

### 10.2 `crates/kovanica-node/tests/htlc_node.rs` (~4 tests)

- `swap_e2e_same_chain` — full two-party swap: Alice creates HTLC-A, Bob
  verifies + creates HTLC-B, Alice redeems B, Bob extracts preimage and redeems
  A; assert both balances.
- `swap_refund_path` — Alice never redeems; Bob refunds B after T_B; Alice
  refunds A after T_A.
- `swap_timeout_ordering_enforced` — `SwapSession::new` rejects
  `timeout_b >= timeout_a`.
- `htlc_rpc_commands` — the four line-RPC commands end-to-end.

### 10.3 `crates/kovanica-ffi/tests/ffi.rs` (+2)

- `htlc_over_ffi` — create/redeem/refund/balance over the FFI surface.
- `swap_session_over_ffi` — `SwapSession` construction + `verify_against`.

### 10.4 Cross-cutting invariants

- **Address-version invariant:** every blue block's spent outputs are validly
  authorized by their address version's rule — HTLC adds the `v0x04` branch
  (redeem by witness length 3, refund by witness length 2).
- **Determinism:** the timeout is the block's **height** (a pure function of the
  DAG, never wall-clock); path discrimination is by witness length; the
  parallel double-spend test asserts deterministic resolution.
- **Activation independence:** HTLC's gate is independent of RFC-001/002/003
  gates; a block may be post-HTLC but pre-script-v2 or vice versa.

---

## 11. Wire & persistence notes

**Format bump: NONE — no testnet reset.**

- HTLC is an **address version in the existing 33-byte `owner` field**; the
  transaction encoding, checkpoint (v5), snapshot, and `kvnc…dag` rendering are
  unchanged.
- Old nodes reject version `0x04` at parse (`VERSION_MAX`) — a **soft
  incompatibility** handled by activation gating, not a wire-format break.
- The checkpoint stays **v5** (RFC-003) — an HTLC output is just an ordinary
  output whose owner is a `v0x04` address; no new per-output fields.
- The snapshot format is unchanged — HTLC adds no block fields; no `_with_htlc`
  readers needed (unlike hybrid).
- **Identity-preserving block replay:** HTLC adds no block fields, so
  `insert_prepared_block` / `insert_raw_block` semantics are unchanged.

---

## 12. Risks & invariants

1. **Determinism.** Timeout uses the block's **height** — a pure function of
   the DAG, never wall-clock. Preimage generated off-chain; the ledger never
   samples randomness. Path discrimination by witness length. The parallel
   double-spend test asserts deterministic resolution.
2. **Format bump: none.** Address version in the existing 33-byte `owner`
   field. **No testnet reset.**
3. **Identity-preserving block replay.** HTLC adds no block fields; no
   `_with_htlc` readers needed (unlike hybrid).
4. **DAG-vs-chain locktime semantics.** `n_lock_time` = absolute block height;
   `height == blue_score` for every block, so the clock is unambiguous. A
   refund tx is valid iff **its own block's** height ≥ timeout. Margin
   `T_A − T_B` must cover DAG propagation latency (off-chain policy). CSV
   deferred to 5.2 (needs per-UTXO creation-height tracking).
5. **CLTV semantics change.** `NonFinalTransaction` changes shipped script-v2
   behavior — own rationale + adversarial tests, **separable commit**. The
   HTLC template does not depend on it.
6. **Activation default.** `HTLC_ACTIVATION_SCORE = 0` = immediately active on
   the existing testnet (consistent with RFC-001/002/003).

---

## 13. Future work (out of scope for this RFC)

- **Time-lock vault (5.2):** CSV real enforcement (BIP-112) with per-UTXO
  creation-height tracking; builds on the CLTV fix from §5.
- **Token staking extensions (5.3):** `stake.rs` already exists; v2 script may
  extend it later.
- **DEX design doc (5.4), VM research gate (5.5):** deferred.
- **Explorer/SPV:** no surface change needed — addresses render generically and
  SPV filters use the 33-byte owner; verify with one test each.

---

*End of RFC-004.*
