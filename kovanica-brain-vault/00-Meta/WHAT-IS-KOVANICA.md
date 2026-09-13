# What is Kovanica?

**Kovanica** is a **BlockDAG** ledger: blocks may reference multiple parents, so the network can produce blocks in parallel and still agree on one order. Consensus follows **GHOSTDAG** (parameter **k = 3**). The native currency is **KVNC**.

The name *kovanica* is Serbo-Croatian for a coin / mint.

## In one minute

| | |
|--|--|
| **Data structure** | BlockDAG (not a single linear chain) |
| **Consensus** | GHOSTDAG linearization + blue/red colouring |
| **State** | UTXO, Ed25519 spends |
| **Work** | Optional real PoW on block ids (`nonce` + work target) |
| **Native asset** | **KVNC** (8 decimals; 1 KVNC = 10⁸ atoms) |
| **Token standard** | **[KVP-102](./KVP-102-NativeTokens.md)** — multi-asset outputs (not ERC-20) |
| **Network today** | **kovanica-testnet** — public HTTP explorer + P2P seed |

## What you can do on testnet

- Explore the DAG and selected chain: [explorer](https://explorer.kovanica.online) / [kovanica.online](https://kovanica.online)
- Use a browser wallet, multisig (KVP-101), network status, origins map
- Run or peer with a node (TCP **9000**; prefer DNS seed, not Cloudflare-proxied HTTP host for P2P)

## Protocol standards (KVP)

Public names map to RFCs:

| Standard | Means |
|----------|--------|
| **KVP-101** | Multisig M-of-N (P2SH) |
| **KVP-102** | Native multi-asset tokens |
| **KVP-103** | Stealth addresses + script v2 |
| **KVP-104** | HTLC atomic swaps (in progress) |

See [KVP.md](./KVP.md).

## What Kovanica is not

- Not an EVM chain and not an ERC-20 contract platform
- Not mainnet yet — treat balances as test-only
- Not financial advice; software may contain bugs

## Go deeper

- [TOKENOMICS.md](./TOKENOMICS.md) — subsidy, fees, KVNC vs KVP-102
- [LEGIT-BOARD.md](./LEGIT-BOARD.md) — public roadmap to a credible project
- RFCs under `docs/RFC-*.md` — normative wire and consensus detail
