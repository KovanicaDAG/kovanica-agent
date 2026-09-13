# Kovanica — Legit board (P0 / P1 / P2)

Actionable checklist to make the project **credibly public**, not just a private monorepo with a testnet UI.

**How to use:** check boxes in PRs that close an item; link the PR next to the row. Status below is the baseline as of the board’s introduction.

| Priority | Goal | Horizon |
|----------|------|--------|
| **P0** | Transparent + explainable | 0–2 weeks |
| **P1** | Usable public testnet | 2–6 weeks |
| **P2** | Mainnet-ready track | 1–3 months |

Related specs: [KVP.md](./KVP.md) · [KVP-102](./KVP-102-NativeTokens.md) · [WHAT-IS-KOVANICA](./WHAT-IS-KOVANICA.md) · [TOKENOMICS](./TOKENOMICS.md)

---

## P0 — Must have (0–2 weeks)

Without these, the project still looks closed.

### P0.1 Public source code
- [ ] Publish `kovanica-protocol` (or a **read-only mirror**) so clone works without invite
- [ ] Link **Source** from `kovanica.online` (footer or Docs)
- [ ] Keep secrets out of the public tree (VPS keys, `.env`, private workflows stay private)

**Done when:** anonymous `git clone` succeeds; site points at the repo.

### P0.2 GitHub Releases (binaries + checksums)
- [ ] Workflow or manual release: `kovanica-node` (linux-x86_64 at minimum)
- [ ] SHA256SUMS file on the release
- [ ] Android APK on the same release (or linked release)
- [ ] Optional: unsigned iOS IPA + sideload note
- [ ] Web “Native wallet” card points at **Releases**, not only Actions artifacts

**Done when:** download works without GitHub login.

### P0.3 One-pager — What is Kovanica
- [x] Draft in-repo: [WHAT-IS-KOVANICA.md](./WHAT-IS-KOVANICA.md)
- [ ] Surface on web (`/docs` section or `/about`)
- [ ] Link from home footer / roadmap

**Done when:** a new visitor gets the pitch in &lt;1 minute without reading RFCs.

### P0.4 Emission & tokenomics (public)
- [x] Draft in-repo: [TOKENOMICS.md](./TOKENOMICS.md) (from code constants)
- [ ] Same numbers on web Docs
- [ ] Explicit **KVNC vs KVP-102** wording everywhere assets are mentioned

**Done when:** supply/subsidy/fee rules are public and match `web/src/lib/api/contract.ts` + node.

### P0.5 Testnet reset policy
- [ ] Write policy: resets only on **wire-format bumps** or safety incidents
- [ ] Announce in release notes / Discord (when channel exists) before wipe
- [ ] Tag epochs if needed (`kovanica-testnet-eN`)

**Done when:** no silent chain wipes.

### P0.6 Reliable web deploy
- [ ] `web-deploy.yml` green on every `web/**` push to `main`
- [ ] Document fallback: VPS `build:vps` + rsync + pm2 (already in team notes)
- [ ] After deploy, smoke: `/`, `/roadmap`, `/network`

**Done when:** KVP labels on `/roadmap` match `main` without manual SSH.

### P0.7 Disclaimer
- [ ] Footer or Docs: testnet software, no investment advice, funds can be lost
- [ ] Optional: maintainer contact (email / GH discussions)

---

## P1 — Serious testnet (2–6 weeks)

Others can run peers and build on the API.

### P1.1 Land KVP-104 (HTLC)
- [x] Rebase RFC-004 / PR branch onto current `main`
- [x] Green consensus tests; merge
- [x] Note on roadmap flips to **Shipped**

**Done when:** HTLC is on `main` with tests; [KVP.md](./KVP.md) status updated.
> ✅ **Done 2026-09-08** — RFC-004 rebased onto `main` (PR #88, merged `fb13741`) after
> main's web typecheck was restored (PR #95). KVP-104 → **Shipped**.

### P1.2 Node HTTP `asset_id` (KVP-102)
- [ ] `/api/utxos` includes `asset_id` per UTXO
- [ ] `/api/history` includes `asset_id` per delta
- [ ] `/api/prepare` (and submit path) accept asset selection already used by web
- [ ] Web AssetPicker shows non-native balances for real

**Done when:** end-to-end KVP-102 send on testnet from the web wallet.

### P1.3 Multiple public seeds / peers
- [ ] ≥2 geographically or org-distinct nodes
- [ ] Bootstrap list published (DNS + IPs where appropriate)
- [ ] Cloudflare: P2P port **not** orange-clouded (seed hostname grey-cloud)

**Done when:** a third party syncs from bootstrap without your laptop.

### P1.4 Run-a-node guide
- [ ] Single doc: build/release binary, ports (`9000`), env (`KOVANICA_PEERS`), disk
- [ ] “Verify tip matches explorer” smoke steps
- [ ] Linked from Docs / WHAT-IS

**Done when:** cold operator follows doc and reaches the selected tip.

### P1.5 Public status surface
- [ ] `/network` (or status subdomain) shows head, peers, PoW, deploy age
- [ ] Optional: simple uptime history

**Done when:** outages are visible without asking in chat.

### P1.6 Security notes (lightweight threat model)
- [ ] Doc: what PoW + GHOSTDAG k protect; what they don’t
- [ ] Key handling: browser wallet vs hardware vs seed files
- [ ] Finality depth / reorg expectations on testnet

**Done when:** `docs/SECURITY.md` (or section) exists and is linked.

### P1.7 Open issue tracker
- [ ] Public Issues enabled on the public repo
- [ ] Bug / feature templates
- [ ] Security contact path (GH Security Advisories or email)

**Done when:** an outsider can file a bug without a private invite.

### P1.8 Spec index
- [ ] Docs index lists KVP-101…104 + RFC links
- [ ] Roadmap stays in sync when status changes

---

## P2 — Mainnet track (1–3 months)

### P2.1 Audit plan
- [ ] Scope: `kovanica-dag` + `kovanica-state` (+ node RPC surface)
- [ ] Candidate firm/researchers + budget range
- [ ] Public target window (month), even if not booked yet

**Done when:** plan is published; not necessarily audit finished.

### P2.2 Reproducible builds
- [ ] Document toolchains (Rust, Node) and lockfiles
- [ ] CI verifies release binary hash from tagged commit

**Done when:** third party rebuild matches release SHA256.

### P2.3 Bug bounty (even small)
- [ ] Rules: in-scope crates, severity, payouts, exclusions
- [ ] Safe harbor language
- [ ] Submission channel

**Done when:** bounty page is live with non-zero clarity (budget can be modest).

### P2.4 Mainnet exit criteria
- [ ] Written checklist, e.g.:
  - [ ] P0 complete, P1.1–P1.4 complete
  - [ ] Audit plan in progress or first report received
  - [ ] ≥N independent nodes for M days
  - [ ] No unresolved critical bugs in consensus
- [ ] Explicit: mainnet date follows criteria, not the reverse

**Done when:** `docs/MAINNET-CRITERIA.md` exists and is linked from roadmap.

### P2.5 Entity & legal blurb
- [ ] Who maintains the reference implementation
- [ ] Jurisdiction-appropriate disclaimers
- [ ] No implied return / investment language on the site

### P2.6 Community home
- [ ] One primary channel (Discord or similar) with moderation rules
- [ ] Link from site; avoid empty multi-platform spam

### P2.7 KVP-102 issuance policy
- [ ] Document current rule: **coinbase mint only**; regular tx cannot mint
- [ ] If policy tags (mint authority) are planned, RFC/KVP amendment
- [ ] Until then, say so on TOKENOMICS / KVP-102

### P2.8 Ops hardening
- [ ] Backups of node data; restore drill once
- [ ] Rate limits / ban persistence verified under load
- [ ] Monitoring alerts (tip stall, disk, peer count)

### P2.9 Optional product polish
- [ ] Hardware wallet path verified on real device
- [ ] Light-node store listing only after signing policy is decided
- [ ] Explorer deep-links stable across deploys

---

## Explicit non-goals (do not block P0–P1)

- CEX listing
- Paid influencer campaigns
- Fake TVL / partnership banners
- Mainnet launch without P2.4 criteria
- Rebrand churn

---

## Suggested sequence

```
Week 1     P0.1 public code · P0.3/P0.4 on web · P0.7 disclaimer
Week 1–2   P0.2 releases · P0.5 policy · P0.6 deploy reliability
Week 2–4   P1.1 HTLC · P1.2 asset_id HTTP
Week 3–6   P1.3–P1.8 network + docs + issues
Month 2–3  P2.x audit track + mainnet criteria + bounty
```

## Definition of “legit v1”

**All P0 checked** and **at least P1.1, P1.2, P1.3, P1.4, P1.7** checked.

That is enough for outsiders to read the code, run a node, hold testnet KVNC, and report bugs—without trusting a private chat.
