# RFC-002 / KVP-102 — Native multi-asset tokens

**Status:** Shipped (core ledger)  
**Public name:** KVP-102 (native multi-asset; **not** an ERC-20)

## Summary

Multi-asset UTXOs with per-asset conservation.  
Coinbase can mint new asset types. Checkpoint format bumped (v4) to carry asset metadata.

## Key behaviours

- Every UTXO carries an `asset_id` (native KVNC is a distinguished id).
- Value conservation is enforced **per asset**.
- Coinbase outputs may mint a new asset or increase supply of an existing one under consensus rules.
- HTTP API exposure of `asset_id` on utxos / history / prepare is still being completed (roadmap “Node HTTP asset_id”).

## Client rules

1. Always treat balances as (asset_id → amount) maps, never a single scalar.
2. `prepare` / `submit` must preserve asset_id on every input and output.
3. Until the HTTP API fully surfaces `asset_id`, the web AssetPicker remains limited.
4. Explorers should badge non-KVNC assets distinctly.

## Open follow-ups (roadmap)

- Full web KVP-102 UX (AssetPicker)
- Token staking & sortition denominated in any KVP-102 asset
- Stable `asset_id` fields on all relevant HTTP endpoints