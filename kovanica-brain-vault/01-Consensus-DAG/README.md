# 01-Consensus-DAG — GHOSTDAG Consensus & Protocol RFCs

**Purpose**: Core consensus mechanics, DAG structure, and all protocol RFC specifications.

## Contents

### Protocol RFCs (Authoritative Specifications)

| File | Description |
|------|-------------|
| [RFC-001-Multisig.md](RFC-001-Multisig.md) | M-of-N multisignature (P2SH), threshold signatures, activation gating |
| [RFC-002-NativeTokens.md](RFC-002-NativeTokens.md) | Multi-asset UTXO outputs, per-asset conservation, coinbase minting |
| [RFC-003-ScriptV2-and-Stealth.md](RFC-003-ScriptV2-and-Stealth.md) | Script v2 (bounded stack machine) + Stealth addresses (one-time keys) |
| [RFC-004-Htlc.md](RFC-004-Htlc.md) | HTLC template (preimage hash + timeout), Tier Nolan atomic swaps |
| [RFC-005-Vault.md](RFC-005-Vault.md) | Time-lock vaults, real CSV (relative locktime), checkpoint v6 |
| [KVP-102-NativeTokens.md](KVP-102-NativeTokens.md) | KVP for native tokens |
| [TOKENOMICS.md](TOKENOMICS.md) | Emission curve, halving schedule, MAX_SUPPLY |

### Skill Summaries (Quick Reference)

| File | Description |
|------|-------------|
| [skills-rfc-001-multisig.md](skills-rfc-001-multisig.md) | Multisig skill summary |
| [skills-rfc-002-multi-asset.md](skills-rfc-002-multi-asset.md) | Native tokens skill summary |
| [skills-rfc-003-stealth-script.md](skills-rfc-003-stealth-script.md) | Stealth + Script v2 skill summary |
| [skills-rfc-004-htlc.md](skills-rfc-004-htlc.md) | HTLC skill summary |
| [skills-rfc-005-vault.md](skills-rfc-005-vault.md) | Vault skill summary |
| [skills-rfc-006-activation.md](skills-rfc-006-activation.md) | RFC-006 activation gating |
| [skills-rfc-006-tokenomics.md](skills-rfc-006-tokenomics.md) | Tokenomics skill summary |
| [rfc-006-tokenomics-numbers.md](rfc-006-tokenomics-numbers.md) | Tokenomics parameters |

### Implementation Skills (from /root/rust/skills/)

| File | Description |
|------|-------------|
| [skills/rust-consensus-ghostdag/SKILL.md](skills/rust-consensus-ghostdag/SKILL.md) | **GHOSTDAG consensus implementation** — k-cluster, blue/red colouring, blue score, mergeset, linearization |
| [skills/rust-consensus-pow/SKILL.md](skills/rust-consensus-pow/SKILL.md) | **Proof-of-Work consensus** — SHA-256d mining, nonce, difficulty, PoW verification |
| [skills/rust-crypto-primitives/SKILL.md](skills/rust-crypto-primitives/SKILL.md) | **Crypto primitives** — signatures, hashes, merkle, commitments, key gen, addresses |
| [skills/rust-merkle-structures/SKILL.md](skills/rust-merkle-structures/SKILL.md) | **Merkle structures** — MPT, MMR, Merkle proofs, inclusion/exclusion, truncatable |

## Key Concepts

- **GHOSTDAG**: Sompolinsky, Wyborski & Zohar (Kaspa protocol)
- **k-cluster**: Blue/red colouring, max blue anticone size = k
- **Selected parent**: Heaviest blue work parent
- **Mergeset**: Blocks merged by a new block
- **Linearization**: Recursive GHOSTDAG order
- **Blue score/work**: Drives chain selection

## Crate Reference

- `crates/kovanica-dag` — DAG + GHOSTDAG consensus core
- `crates/kovanica-state` — UTXO ledger applied in GHOSTDAG order