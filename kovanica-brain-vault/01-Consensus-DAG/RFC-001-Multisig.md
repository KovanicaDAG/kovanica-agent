# RFC-001 — M-of-N Multisignature (Witness Payloads & P2SH)

- **Status:** Shipped (implemented in `kovanica-state`)
- **Reference implementation:** `crates/kovanica-state/src/multisig.rs`,
  `crates/kovanica-state/src/keys.rs`, `crates/kovanica-state/src/ledger.rs`
- **Consensus test suite:** `crates/kovanica-state/tests/multisig_consensus.rs` (35 tests)
- **Activation:** gated on blue score (see [Activation gating](#activation-gating))

This document is the specification that the multisig code in `kovanica-state`
references as "RFC-001". It describes the redeem-script format, address
derivation, witness layout, M-of-N semantics, and the consensus activation gate.
It is grounded in the shipped implementation — do not change the formats here
without changing the code, and vice versa.

---

## 1. Overview

A **multisig** (M-of-N) output locks value behind a *threshold redeem script*
rather than a single Ed25519 public key. Spending it requires **exactly `M`**
valid signatures drawn from a set of **`N`** authorized public keys.

Multisig outputs use **Version 0x01 (P2SH — Pay-to-Witness-Script-Hash)**
addresses, distinct from the ordinary **Version 0x00 (P2PK)** single-key
addresses. The two coexist in the ledger; a P2SH output is spent by revealing
the redeem script and the threshold signatures in the input's witness stack.

The design follows the Bitcoin P2SH model (script-hash locking, script revealed
at spend time) adapted to this protocol's primitives: **BLAKE3** for hashing and
**Ed25519** for signatures.

---

## 2. Redeem script format

A redeem script is a canonical byte string:

```
[M (1 byte), N (1 byte), PubKey_1 (32 bytes), ..., PubKey_N (32 bytes)]
```

- `M` — required threshold of valid signatures (`1 <= M <= N`).
- `N` — total number of authorized public keys (`1 <= N <= 16`).
- `PubKey_i` — a raw 32-byte Ed25519 public key.

The total length is exactly `2 + 32 * N` bytes.

### 2.1 Validation rules (`MultisigScript::parse` / `MultisigScript::new`)

A script is **strictly validated** at parse time and rejected if any of the
following holds:

- `M < 1` (threshold must be at least 1).
- `N < 1` (at least one key required).
- `M > N` (threshold cannot exceed the key count).
- `N > 16` (`MAX_MULTISIG_KEYS`).
- The byte length does not equal `2 + 32 * N` (truncated or trailing garbage).
- Any public key is not a valid Ed25519 point (`VerifyingKey::from_bytes` fails).
- Any two public keys are identical (duplicate keys rejected).

### 2.2 Constants

| Constant | Value | Meaning |
|---|---|---|
| `MAX_MULTISIG_KEYS` | `16` | Maximum `N` (and therefore maximum `M`) |
| `Address::VERSION_P2SH` | `0x01` | Address version byte for multisig |

---

## 3. Address derivation

A multisig output is locked to a **P2SH address** derived from the redeem
script:

```
script_hash = BLAKE3(redeem_script_bytes)      # 32 bytes
address     = 0x01 || script_hash              # 33 versioned bytes
```

- `MultisigScript::script_hash()` returns `BLAKE3(encode())`.
- `MultisigScript::address()` returns `Address::p2sh(script_hash)`.
- `Address::from_script(redeem_script)` computes the same from raw script bytes.

The address is the canonical 33-byte versioned form (`version byte || 32-byte
payload`), where the payload is the BLAKE3 script hash. For humans it renders as
`kvnc…dag` (base58 over the 33 bytes) exactly like P2PK addresses, but with the
`0x01` version byte; `Address::parse` accepts 66-hex, 64-hex (legacy P2PK), or
`kvnc…dag`.

---

## 4. Witness layout

A spend of a P2SH output carries a **witness stack** on its `TxInput`:

```
witness[0]        = raw redeem script bytes (the `[M, N, pk1, ..., pkN]` encoding)
witness[1..=M]    = exactly M valid 64-byte Ed25519 signatures
```

The witness stack therefore has exactly `1 + M` elements.

### 4.1 Spend validation (`verify_threshold_signatures`)

When spending a P2SH output, the ledger (`ledger.rs`) enforces, in order:

1. **Script-hash match** — `BLAKE3(witness[0])` must equal the output's address
   payload (`ScriptHashMismatch` otherwise).
2. **Script validity** — `witness[0]` must parse as a valid `MultisigScript`
   (`InvalidRedeemScript` otherwise).
3. **Witness count** — the stack must have exactly `1 + M` elements
   (`InvalidWitnessCount` otherwise).
4. **Signature size** — every signature must be exactly 64 bytes
   (`BadSignatureSize` otherwise).
5. **Threshold verification** — exactly `M` signatures must verify against
   **distinct** authorized keys over the transaction `sighash`:
   - Each signature must verify under a public key in the script that has not
     already been used by an earlier signature in the stack.
   - Duplicate signatures are rejected (`DuplicateSignature`).
   - A signature that verifies under no unused authorized key is rejected
     (`BadSignature`).

### 4.2 Sighash

The `sighash` is `BLAKE3` over the **witness-free** canonical encoding of the
transaction (`Transaction::sighash`). Signatures are attached to the witness
stack and therefore do not participate in the hash — this is what makes the
sighash deterministic and independent of which signers sign.

### 4.3 Construction helpers

- `TxInput::multisig(outpoint, redeem_script, signatures)` builds the witness
  stack (`[script, sig_1, ..., sig_M]`).
- `Transaction::signed_multisig(outpoint, redeem_script, signers, outputs, tag)`
  computes the sighash, signs with each signer, and attaches the witness.

---

## 5. M-of-N semantics

- **`N`** is the total number of authorized keys, `1 <= N <= 16`.
- **`M`** is the threshold, `1 <= M <= N`.
- A spend is valid **iff** the witness carries **exactly `M`** valid signatures,
  each under a **distinct** authorized key, over the transaction sighash.
- Providing **fewer** than `M` signatures, **more** than `M`, a duplicate, or a
  signature from an unauthorized key all fail validation.

The threshold is enforced by the *count* of valid distinct signatures, not by
any ordering of the keys in the script. Any `M` of the `N` keys may sign.

---

## 6. Activation gating

Multisig (P2SH) is a **consensus upgrade** gated on **blue score** so that
pre-activation blocks cannot create or spend P2SH outputs.

- Default activation threshold: `MULTISIG_ACTIVATION_SCORE = 0` (i.e. active
  from genesis by default).
- Configurable per ledger via `Ledger::set_multisig_activation_score(score)`;
  readable via `Ledger::multisig_activation_score()`.
- The gate is **inclusive**: a block is *pre-activation* when
  `blue_score <= activation_score`.

### 6.1 Pre-activation rules

While `blue_score <= activation_score`, the ledger rejects (`PreActivationMultisig`):

- Any **output** (regular transaction or coinbase) whose owner is a P2SH address.
- Any **spend** of a P2SH output, or any input whose witness stack has more than
  one element (i.e. any multisig-style witness).

### 6.2 Post-activation

Once `blue_score > activation_score`:

- P2SH outputs may be created and spent normally.
- Legacy P2PK single-signature spends remain valid forever (the upgrade is
  additive — it does not disable P2PK).

The gate is threaded through both the incremental `Ledger` path and the
batch `apply_dag`/`apply_block` paths, so activation is enforced identically
regardless of how a chain is applied.

---

## 7. Consensus & adversarial coverage

`crates/kovanica-state/tests/multisig_consensus.rs` (35 tests) covers:

1. Positive M-of-N threshold spends: 1-of-1, 2-of-2, 2-of-3 (all subsets),
   3-of-5, 16-of-16 (max keys), 1-of-16 (min threshold, max keys).
2. Invalid M/N combinations: M=0, N=0, M>N, N>16, max byte values (255/255).
3. Malformed scripts: too short, truncated, trailing garbage, duplicate
   pubkeys, invalid Ed25519 points.
4. Script-hash / address mismatches: wrong script, single-bit flips.
5. Witness-count anomalies: missing signatures, excess signatures, empty
   witness.
6. Cryptographic integrity: corrupted signatures, unauthorized signers, wrong
   sighash (replay), wrong signature size.
7. Duplicate-signature attacks.
8. Consensus activation gating: pre vs post activation, exact boundary
   transition, legacy P2PK permanently valid post-activation.
9. Mixed blocks (P2PK + P2SH coexisting) and mixed-input transactions.
10. Cross-type witness mismatch, parallel-DAG double-spend resolution by
    linearization, and ledger snapshot/replay roundtrip.

---

## 8. Wire & persistence notes

- P2SH addresses are ordinary 33-byte versioned addresses on the wire; no
  separate address type exists.
- Multisig transactions are ordinary transactions whose inputs carry the
  multisig witness stack; they serialize through the existing canonical
  transaction encoding and survive snapshot/checkpoint replay unchanged.
