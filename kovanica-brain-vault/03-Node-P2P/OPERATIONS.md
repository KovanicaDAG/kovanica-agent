# Operations runbook — `kovanica-testnet`

> Source of truth for live topology, deploy pipeline, DNS, and incident
> lessons. Keep in sync with reality in the same change that alters any of it.
> (The vault copy was archived to `Obsidian-Vault/KovanicaDAG/_archive/` on
> 2026-09-05 — this file is the only live copy.)

*Updated: 2026-09-03*

## 1. Topology (all on VPS `srv1745734`, 145.223.116.178)

| Component | Where | Notes |
| --- | --- | --- |
| **seed1** (primary) | systemd `kovanica-explorer`, P2P `:9000`, HTTP loopback `:8080` | auto-mines 1 block/min (`KOVANICA_MINE=1 KOVANICA_MINE_SECS=60`), set after the 2026-09-03 liveness stall |
| **seed2** (validation instance) | systemd `kovanica-seed2`, P2P `:9001`, HTTP loopback `:18080` | same host as seed1 — proves deploy-seed.sh, no resilience gain |
| **web** (kovanica.online + wallet + map + explorer pages) | pm2 `kovanica-web`, `127.0.0.1:3010` | built via `npm run build:vps`, deployed to `/root/kovanica-web/.output` |
| nginx | `/etc/nginx/sites-enabled/explorer.kovanica.online` | `/api/*`→`:8080`, pages→`:3010`, `/download/*`→`/var/www/kovanica-dist/` |
| Node binaries (public) | `/var/www/kovanica-dist/{kovanica-node-linux-x64,-arm64,install.sh}` | served at `https://explorer.kovanica.online/download/…` |
| Chain data (seed1) | `/root/kovanica-data` (`KOVANICA_DATA`) | **outside the git tree** so runtime writes never dirty it |
| Soak logs | `/root/kovanica-data/soak/` | `testnet-measure.py`, 24h runs |

Current network: genesis `596874eac2d08723b12fc3cac8f891493139200da4818594c6632b3fe4d0048f`
(the 9a live-sync spike genesis; unchanged since that gate). The 2026-08-24
runbook still listed `76cc019d…` — that hash is stale after the later reset.
The pre-reset chain (genesis `27d5f750…`, 127 blocks) was lost on 2026-08-24 —
its data dir was inside a directory that got deleted while the old process held it.

## 2. Deploy pipelines

### Rust node (explorer/seeds) — GitHub Actions `.github/workflows/deploy.yml`
- Trigger: push to `main`; gated by `DEPLOY_ENABLED=true` repo variable (set).
- Secrets: `VPS_HOST=145.223.116.178`, `VPS_USERNAME=root`, `VPS_PRIVATE_KEY` (= local `~/.ssh/github_actions`, authorized in `~/.ssh/authorized_keys`).
- **SSH port is 2222, not 22** — upstream filtering (Hostinger-level) times out GitHub runner connections on :22 after repeated logins. sshd listens on both.
- Steps: cargo test/clippy/fmt gate → release build artifact → scp to `/root/bin/kovanica-node` → `systemctl stop kovanica-explorer` → atomic `install`+`mv` to `/usr/local/bin/kovanica-node` (in-place cp hits ETXTBSY — seed2 executes the same path) → `systemctl start kovanica-explorer` → `systemctl restart kovanica-seed2`.
- **Process manager: systemd everywhere (decision 2026-08-24).** pm2 was retired for Kovanica node processes after a pm2-vs-systemd port fight; it remains only for unrelated apps on the VPS. All three nodes are systemd units now (`kovanica-explorer`, `kovanica-seed2`, `kovanica-seed3`).

### Web app — manual for now
```
cd web && npm run build:vps
rsync -a --delete .output/ /root/kovanica-web/.output/
pm2 restart kovanica-web
```

### New remote seed — `scripts/deploy-seed.sh`
```
./scripts/deploy-seed.sh root@<host> --name seed3 --mine --peers seed.kovanica.online:9000
```
Ships a `git archive` tarball (no clone auth needed), installs prereqs + swap,
builds on-target, systemd unit `kovanica-seed3`, opens only the P2P port,
verifies genesis match against seed1.

## 3. DNS (Cloudflare)

- Zone `kovanica.online`: `6fc91866edb8c9fab9fd2458857b5939`
- API token: `/root/cloudflare-token` — **always call with `curl -4`**: the token's IP filter rejects this box's IPv6 egress ("Cannot use the access token from location").
- Records (seeds must be **DNS-only / grey cloud** — proxying breaks raw TCP :9000):

| Name | Type | Content | Proxy |
| --- | --- | --- | --- |
| `seed.kovanica.online` | A | `145.223.116.178` | DNS only |
| `seed.kovanica.online` | AAAA | `2a02:4780:41:1f43::1` | DNS only |
| `seed3.kovanica.online` | A | `3.79.148.71` | DNS only |
| `explorer/www/app/wallet/trader/bot/dash/kovi` | A | `145.223.116.178` | proxied |
| `opencode` | A | `145.223.116.178` | DNS only |

## 4. Hard-won incident lessons (do not relearn)

1. **Port 22 from GitHub runners gets filtered** after several rapid deploys:
   `dial tcp :22 i/o timeout` with zero packets reaching sshd. Fix = alternate
   port 2222 (workflow `port:` fields + ufw). If it recurs on 2222, suspect the
   provider shield again — rotate the port or self-host the runner.
2. **Ubuntu socket-activated sshd ignores bare `Port` lines** until restarted
   through `ssh.socket`. Editing `/etc/ssh/sshd_config` alone can leave you with
   a half-bound state or kill ssh.socket (`Address already in use`). After any
   port change: `systemctl daemon-reload && systemctl restart ssh.socket ssh`,
   then verify with `ss -tlnp | grep -E ':22|:2222'` **and an actual login**.
3. **ETXTBSY**: a running binary cannot be overwritten. Always stop → cp → start.
4. **Deleted-inode trap**: replacing the binary file does NOT update a running
   process — it keeps serving the old bytes with `(deleted)` in
   `/proc/<pid>/exe`. After any binary swap, restart the service and confirm
   `readlink /proc/$(pm2 pid <svc>)/exe` matches the disk file.
5. **Never put runtime state inside a git working tree** (the lost-chain
   incident). Data lives in `/root/kovanica-data`, outside any checkout.
6. **Metrics crate versions must align**: `metrics` minor version must equal
   what `metrics-exporter-prometheus` uses internally, or emissions land in a
   noop recorder of the other version's global slot. Also keep
   `default-features = false` on the exporter (we render `/metrics` ourselves;
   the http-listener feature drags openssl and breaks ARM cross-builds).
7. **DHT handshake contacts**: `Mesh::connect` registers mutual routing-table
   contacts; eclipse resistance depends on it. See AGENTS.md §8.

## 5. Monitoring (Prometheus on the VPS, armed 2026-08-24)

- Prometheus 2.45 runs as systemd `prometheus`, UI on `127.0.0.1:19080`
  (node metrics listener owns :9090). TSDB retention 30d.
- Targets: `seed.kovanica.online` = local node `127.0.0.1:9090` (direct);
  `seed3.kovanica.online` via SSH tunnel unit `kovanica-tunnel-seed3`
  (`127.0.0.1:19090` → seed3 `:9090`; metrics ports stay firewalled).
- Rules: `/etc/prometheus/alerting_rules.yml` (repo copy is source of truth;
  keep `humanizeBytes`-style non-existent template functions out — promtool
  rejects them and the whole file fails to load). 15 alerts + 9 recording rules.
- `kovanica_peer_count` samples peers that answered the last sync round
  (`live_peers`), refreshed every ~5 s in the explorer idle tick.
- **Baseline (2026-08-24 16:20 UTC):** height seed=448 / seed3=447,
  peer_count 2/2 both, mempool 0, orphans 0, blue_score≈height, no reorgs.
- **Soak snapshot (2026-08-31 ~09:10 UTC)** — public explorer API
  (`GET /api/head`, `/api/bootstrap`, `/api/state`):

  | Field | Value |
  | --- | --- |
  | network | `kovanica-testnet` |
  | genesis | `596874eac2…d0048f` |
  | blocks / chain_len | **3817** |
  | blue_score / blue_work | 3816 / 3816 |
  | tips | 1 (linear selected chain) |
  | k | 3 |
  | PoW | on; per-block `work=1` (blue_work == blue_score) |
  | subsidy | 200 KVNC / block (20_000_000_000 atoms) |
  | supply | 76_340_000_000_000 atoms = 3817 × subsidy (coinbase-only, checks) |
  | mempool | 0 |
  | advertised peers | `seed2.kovanica.online:9001`, `seed3.kovanica.online:9000` |
  | mining | true (`KOVANICA_MINE_SECS=60`) |

  Rate vs plan:

  | Window | Δ blocks | Δ time | rate |
  | --- | --- | --- | --- |
  | 2026-08-24 16:20 → 08-29 18:20 | +1394 (448→1842) | ~5.08 d | **11.4 blk/h** (~5.3 min/block) |
  | 2026-08-29 18:20 → 08-31 09:10 | +1975 (1842→3817) | ~38.8 h | **50.9 blk/h** (~1.18 min/block) |
  | whole soak 08-24 → 08-31 | +3369 | ~6.7 d | 20.9 blk/h (~2.9 min/block avg) |

  The 5×-slow window after the genesis reset was difficulty retarget, not a
  stall. The last ~39 h recovered to ~1.2 min/block, in range of the 1/min
  mine interval. **Do not retune `k`, finality depth, payload pruning, or
  the difficulty window on this snapshot** — the retarget is doing its job.
  Revisit after another week of data.

  Caveats (cannot close ANT-16 from the public API alone):
  - `/metrics` is **not** public (`explorer.kovanica.online/metrics` → 404).
    Orphan rate, propagation latency, reorg depth, disk, and `live_peers`
    still need a VPS Prometheus scrape (`127.0.0.1:19080`).
  - `mesh.nodes[0].peers` is the in-process demo mesh (empty) — not the
    P2P overlay. Overlay health is the advertised `peers` list + Prometheus
    `kovanica_peer_count`.

- **Soak snapshot (2026-09-03)** — captured from public API + VPS scrape:

  | Field | Value |
  | --- | --- |
  | network | `kovanica-testnet` |
  | genesis | `596874eac2…d0048f` |
  | height / chain_len | **5239** |
  | blue_score / blue_work | 5238 / 5238 (linear, tips=1) |
  | k / PoW / work | 3 / on / 1 |
  | min_fee | 40_000 atoms |
  | subsidy / supply | 200 KVNC/block / 104_780_000_000_000 atoms ✓ |
  | advertised peers | `seed2.kovanica.online:9001`, `seed3.kovanica.online:9000` |

  - **Delta vs 08-31 (3817→5239):** +1422 blk over ~62.5 h ≈ **2.64 min/block**.
  - **Delta vs 08-24 baseline (448→5239):** +4791 blk over ~223 h ≈ **2.80 min/block**
    (9+ day soak). No retune recommended — linear chain, all params stable.
  - **Monitoring finding (2026-09-03):** seed is `KOVANICA_MINE=0`, so the
    production-gated gauges (`block_height`, `dag_blue_score`, mempool) never
    register on `/metrics` — only `peer_count` + http counters render. seed3's
    deployed binary renders zero `kovanica_*` series (predates the metrics
    rewrite, commit `c8590a5`). Both are tracked in the repo soak snapshot
    (`docs/soak-snapshot-2026-09-03.md`) and addressed by protocol PR #72
    (surface passive chain-head gauges on every insert) + a seed3 redeploy.
  - **seed3 tunnel restored 2026-09-03:** `kovanica-tunnel-seed3` was stuck
    `activating` (its `seed3` alias pointed `IdentityFile` at a broken symlink
    `/root/.ssh/id_ed25519`). Repointed to `/root/.ssh/aws_seed3`; both
    Prometheus targets are now `up`.
  - **Incident 2026-09-03 — chain stalled at 5239, seed mining re-enabled:**
    height held at 5239 for ~2 h (tip pinned) because seed1 was `KOVANICA_MINE=0`
    and the independent AWS miner seed3 was down, so no node was producing.
    Fix: `KOVANICA_MINE=0→1` on
    `/etc/systemd/system/kovanica-explorer.service` (unit backed up), daemon-reload
    + restart. Height resumed and holds ≥1/min (5259+ at 09-03 ~02:50 local).
  - **seed3 OOM-crash-loop (2026-09-03) — the independent AWS miner is down:**
    seed3 SSH works from the VPS (`/root/.ssh/aws_seed3`, key comment
    `kovanica-seed3-aws`), but port 22 is **intermittent** from the VPS
    (repeated `Connection timed out during banner exchange` — transient
    AWS-side throttling). Its `kovanica-node` is killed by the kernel OOM killer
    at **~790–794 MB anon RSS** (`dmesg`: `Out of memory: Killed process
    kovanica-node …`) on a **913 MB** EC2 instance — it boots, prints the
    explorer/metrics lines, then is SIGKILLed ~17 s later, so `kovanica-seed3`
    flips `active`/`activating` forever.
    - **Resize status (2026-09-03): NOT yet applied.** Despite a request for
      2 GB, seed3 is still `t3.micro` / `MemTotal 935068 kB` (~913 MB), same
      instance `i-084b4ce52d6c63678`, ~9 days uptime (no stop/start/reboot —
      required for a type change to take effect). A real resize at the AWS
      level has not landed on this box.
    - **Stopgap attempted (incomplete):** set `vm.swappiness=100` (did not stop
      the OOM on its own); began adding a systemd drop-in
      `/etc/systemd/system/kovanica-seed3.service.d/oom.conf` with
      `OOMScoreAdjust=-1000` so the node spills to the 2 GB swap instead of
      being OOM-killed — **write unconfirmed** (SSH dropped mid-operation).
      Next action once reachable: verify the drop-in exists, then
      `daemon-reload && restart` and watch RSS/swap.
    - **Real fix** (needs AWS): resize to ≥ 2 GB (ideally `t3.small` @ 2 GB or
      the 4 GB Oracle Always-Free tier), then redeploy the current binary
      (seed3's is 2026-08-24, pre-metrics `c8590a5`) so it also reports the
      passive gauges (`kovanica_block_height`/`kovanica_dag_blue_score`) and
      can hold `KOVANICA_MINE=1` mining at current chain size.
    - **Primary chain unaffected:** the VPS seed (`KOVANICA_MINE=1`) is the
      reliable producer and is healthy/advancing (5290+); PR #72 post-deploy,
      its `/metrics` now shows `kovanica_block_height`/`kovanica_dag_blue_score`
      (e.g. 5277) on both `:9090` and explorer `/metrics` `:8080`.

## 6. Quick commands

```sh
# Health
curl -s http://127.0.0.1:8080/api/head          # seed1 head
systemctl status kovanica-seed2                  # seed2
curl -s http://127.0.0.1:19080/api/v1/targets    # Prometheus targets (jq .data)
curl -s http://127.0.0.1:9090/metrics | head     # seed1 Prometheus series

# Restart after binary swap (auto-deploy does this; manual equivalent)
sudo install -m755 ~/bin/kovanica-node /usr/local/bin/kovanica-node.new \
  && sudo mv -f /usr/local/bin/kovanica-node{.new,}
sudo systemctl restart kovanica-explorer kovanica-seed2

# Watch sync/mining logs
journalctl -u kovanica-seed2 -f
journalctl -u kovanica-explorer -f

# Cold bootstrap check (pristine node pulls from hostname)
KOVANICA_DATA=/tmp/cbt KOVANICA_LISTEN=127.0.0.1:19000 \
KOVANICA_PEERS=seed.kovanica.online:9000 /usr/local/bin/kovanica-node explorer 127.0.0.1:18081
```

## 7. Free hosting candidates for the next off-box seed

| Provider | Offer | Verdict |
| --- | --- | --- |
| Oracle Cloud Always Free ⭐ | ARM A1 4 OCPU/24GB (+2 micro AMD), free forever | best; needs card; capacity varies by region |
| Google Cloud e2-micro | 1 VM free forever (us-west1/central1/east1) | solid fallback |
| AWS Free Tier | ~$200 credits / 6 mo (new accounts); Lightsail 3-mo free | temporary seeds only |
| DigitalOcean | $200 / 60-day trial credits | temporary |
| Vultr | ~$300 / 30-day trial credits | temporary |
| Hetzner | ~€4.5/mo CX22 | not free but reliable EU permanent option |
| Own hardware (RPi/laptop) | free forever behind port-forward or tailscale | genuinely free; needs reachable TCP :9000 |

Cloudflare Tunnel is NOT suitable for seeds (no raw public TCP without client agents).

Roadmap naming: **seed3** = first true off-box node — shipped 2026-08-24 as
AWS EC2 `t3.micro` in eu-north-1 (Amazon Linux 2023, systemd
`kovanica-seed3`, mining on). DNS `A seed3.kovanica.online` (DNS-only) is live;
joining every node's `KOVANICA_PEERS` is the follow-up.

## 8. Seed backup & restore (A8)

Backups are encrypted **at source** before they touch disk. The passphrase is
read from `KOV_BACKUP_PASSPHRASE` or `KOV_BACKUP_PASSPHRASE_FILE`; it is never
passed as a command-line argument and is never committed. Backups are stored in
`/root/kovanica-backups` with permissions `700` on the directory and `600` on
the files.

The scripts back up the node data directory (`data/` or `$KOVANICA_DATA`) and
any wallet seed files matching `*.miner`, `*.seed`, `*.wallet`, or `*.key`.

### Create a backup

```sh
# from the repo
KOV_BACKUP_PASSPHRASE="$(cat /run/secrets/kov-backup-passphrase)" \
  ./scripts/backup-node.sh

# or point at the production data directory
KOV_BACKUP_PASSPHRASE="..." ./scripts/backup-node.sh --data /root/kovanica-data
```

Dry-run first to see what would be captured:

```sh
./scripts/backup-node.sh --dry-run --data /root/kovanica-data
```

Options:
- `--data DIR` — data directory to back up (default: `./data`, else `/root/kovanica-data`)
- `--out DIR` / `--backup-dir DIR` — destination (default: `/root/kovanica-backups`)
- `--name NAME` — backup set name (default: hostname)
- `--retention N` — keep the newest `N` sets (default: 7)
- `--dry-run` — show sizes and paths without writing anything

### Restore from backup

```sh
KOV_BACKUP_PASSPHRASE="..." ./scripts/restore-node.sh --data-dir /root/kovanica-data
```

The script picks the newest data and seed archives in the backup directory. To
use specific archives:

```sh
KOV_BACKUP_PASSPHRASE="..." ./scripts/restore-node.sh \
  --data-archive /root/kovanica-backups/srv1745734-data-20260828-000000.tar.gz.enc \
  --seed-archive /root/kovanica-backups/srv1745734-seeds-20260828-000000.tar.gz.enc \
  --data-dir /root/kovanica-data
```

Verify an archive without extracting:

```sh
KOV_BACKUP_PASSPHRASE="..." ./scripts/restore-node.sh --verify-only \
  --data-archive /root/kovanica-backups/srv1745734-data-20260828-000000.tar.gz.enc
```

Restore will refuse to overwrite a non-empty target directory unless `--force`
is given.

### Restore drill

Run at least once per quarter:

```sh
mkdir -p /tmp/kov-restore-drill
KOV_BACKUP_PASSPHRASE="..." ./scripts/restore-node.sh \
  --data-dir /tmp/kov-restore-drill/data --force
# start a throwaway node against the restored data and check head matches seed1
KOVANICA_DATA=/tmp/kov-restore-drill/data KOVANICA_PEERS=seed.kovanica.online:9000 \
  /usr/local/bin/kovanica-node explorer 127.0.0.1:18081 &
curl -s http://127.0.0.1:18081/api/head | jq .genesis
```
