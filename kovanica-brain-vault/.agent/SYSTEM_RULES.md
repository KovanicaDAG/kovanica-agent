# Agent Directives & Technical Invariants
1. Zero Unsafe: `#![deny(unsafe_code)]` across all protocol crates.
2. Unit Precision: 1 KVNC = 10^8 atoms. Checked integer math only.
3. Patch Guard: Fail-closed; all proposals must pass sandbox verification.
