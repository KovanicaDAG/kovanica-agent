---
source: skills/ghostdag-notes/SKILL.md
name: ghostdag-notes
synced_at: 2026-09-12T08:33:08.793336+00:00
synced_from: skills
tags: [skill, kovanica]
---
# ghostdag-notes — synced from skills/ghostdag-notes/SKILL.md

> This note was auto-synced from the skill file.
> Last synced: 2026-09-12T08:33:08.793336+00:00

# GHOSTDAG Notes for Kovanica (k=3)

## Core parameters

- `k = 3` (fixed for current testnet / RFC-006 era)
- Chain selection work source = **blue work** (real PoW)
- Hybrid admission (Stage 3 vision): PoW blocks + VRF-staked blocks
- Staked blocks pin nominal work so cheaply-inflatable blue weight cannot dominate selection

## Practical implications of k=3

| Topic | Implication |
|-------|-------------|
| Finality depth | Expect deeper confirmation targets than Bitcoin's 6; practical wallets often wait for blue-score advance of several k-windows |
| Reorg risk | Parallel blocks in the anticone are normal; a block is only "final" once it is well inside the selected chain and its anticone is stable |
| Blue vs red | Blue blocks contribute to selected-chain work; red blocks are still stored but do not extend the selected tip's work |
| Parallel minting | Two blocks in each other's anticone can each claim a full subsidy → this is exactly why `native_minted` + `MAX_SUPPLY` hard-cap exists |

## Interaction with RFC-006 tokenomics

- Every block's view carries `native_minted` inherited from its **selected parent** + its own coinbase claim.
- Because GHOSTDAG can accept parallel blocks, the cumulative counter (not the simple curve sum) is the real supply ceiling.
- A coinbase that would exceed `MAX_SUPPLY` is rejected even if the pure geometric curve still has room.

## Testing & analysis tips

1. When writing consensus tests, always construct both a selected_parent chain and an anticone of width ≤ k.
2. Verify that `native_minted` on a block equals selected_parent's value + this block's claim (or is rejected).
3. For wallet UX, prefer "blue-score confirmations" or "depth in selected chain" over raw block height when showing finality.
4. Explorers should visualise the GHOSTDAG graph (selected chain highlighted, anticone visible) — the public explorer already does this.

## Security-budget note

Security budget per block = subsidy + 25 % of fees.  
As subsidy decays, fee revenue and (later) VRF stake become more important. GHOSTDAG blue-work remains the ultimate chain-selection signal; stake only gates admission of staked blocks.
