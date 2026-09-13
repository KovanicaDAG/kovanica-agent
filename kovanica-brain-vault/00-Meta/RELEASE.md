# Release checklist

Use this checklist when cutting a new kovanica-protocol release. The goal is to
make every release reproducible and to avoid surprise breakage from floating
toolchain or base-image versions.

## Before the release

- [ ] Pick the next version using SemVer (e.g. `0.3.0`).
- [ ] Update `Cargo.toml` `[workspace.package] version` to the new version.
- [ ] Update `rust-toolchain.toml` `channel` to the Rust release used for the
      full CI run. Do not leave it on `stable` or `beta`.
- [ ] Pin base images:
  - [ ] GitHub Actions runners use a pinned image (`ubuntu-24.04`, not
        `ubuntu-latest`).
  - [ ] `scripts/deploy-seed.sh` targets a pinned OS base image in your infra
        code (e.g. Ubuntu 24.04 LTS AMI / Debian 12).
- [ ] Run `cargo update` and commit the refreshed `Cargo.lock` so the build is
      reproducible (`--locked` builds use this exact lockfile).
- [ ] Open a release PR and verify the full CI matrix:
  - [ ] `cargo fmt --check`
  - [ ] `cargo clippy --all-targets -- -D warnings`
  - [ ] `cargo test --workspace`
  - [ ] `cargo build --release --workspace --locked`
  - [ ] Web build: `cd web && npm ci && npm run typecheck && npm run lint && npm run build:vps`
- [ ] Run a restore drill with the latest `scripts/backup-node.sh` output:
      `KOV_BACKUP_PASSPHRASE="..." ./scripts/restore-node.sh --verify-only`
- [ ] Write the `CHANGELOG.md` entry for this version.

## Cutting the release

- [ ] `git checkout -b release/vX.Y.Z`
- [ ] Commit the version-bump and changelog changes.
- [ ] Create a signed tag: `git tag -s vX.Y.Z -m "kovanica-protocol vX.Y.Z"`
- [ ] Push the tag: `git push origin vX.Y.Z`
- [ ] Open/merge the release PR to `main`.

## After merge

- [ ] Confirm the Rust node deploy workflow reaches the VPS and the seed
      restarts cleanly (`systemctl status kovanica-explorer`).
- [ ] Confirm the web deploy workflow runs and the app is reachable behind
      nginx on the configured loopback port (default `127.0.0.1:3010`). **Do
      not expose port 3000 publicly.**
- [ ] Verify seed backups are still created successfully:
      `./scripts/backup-node.sh --dry-run`.
- [ ] Update Obsidian-Vault release notes.

## Secrets / credentials

- Never commit `.env` files, private keys, or the backup passphrase.
- `BACKUP_PASSPHRASE` / `KOV_BACKUP_PASSPHRASE` is the single key for all
  node backups. Store it in the password manager / HSM that is the source of
  truth; without it backups are unusable.
