# Hermes Agent Pendrive_X

Hermes Agent Pendrive_X is a portable launcher for the [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent). It keeps the Hermes checkout, runtimes, and portable user data under this project directory so you can run it from a local folder or removable drive.

## What’s included

- Windows and macOS/Linux launchers with verifiable first-run runtime setup.
- Reproducible, checksum-verified runtime manifests for all supported platforms.
- Read-only diagnostics command to inspect platform, runtimes, virtualenv, and dependencies.
- Upgrades with change previews, metadata backups, and documented rollback recovery.
- Full backup and restore workflow with path preservation and SHA-256 verification.
- Isolated runtime cache and Hermes virtual environment.
- Persistent user data in `data/`.
- Optional password-based encryption for selected files in the data vault.
- Utilities for profiles, health reports, MCP configuration, and optional S3 uploads.
- A small optional Electron launcher.

## Supported platforms and versions

| Platform | Architecture | Supported OS Versions | Python Runtime | Node.js | uv | ripgrep |
| --- | --- | --- | --- | --- | --- | --- |
| Windows | x64 (`x86_64`) | Windows 10, Windows 11, Server 2019+ | `3.11.10+20241016` | `22.14.0` LTS | `0.6.8` | `14.1.1` |
| Linux | x64 (`x86_64`) | Ubuntu 20.04+, Debian 11+, Fedora 38+, glibc 2.28+ | `3.11.10+20241016` | `22.14.0` LTS | `0.6.8` | `14.1.1` |
| Linux | arm64 (`aarch64`) | Ubuntu 20.04+, Debian 11+, glibc 2.28+ | `3.11.10+20241016` | `22.14.0` LTS | `0.6.8` | `14.1.1` |
| macOS | arm64 (`Apple Silicon`) | macOS 12 (Monterey) or later | `3.11.10+20241016` | `22.14.0` LTS | `0.6.8` | `14.1.1` |
| macOS | x64 (`Intel`) | macOS 12 (Monterey) or later | `3.11.10+20241016` | `22.14.0` LTS | `0.6.8` | `14.1.1` |

All downloaded runtime archives are cryptographically verified against SHA-256 checksums defined in [`scripts/manifests/runtimes.json`](scripts/manifests/runtimes.json). If any download fails verification, setup halts immediately to prevent running corrupted binaries.

## Quick start

1. Clone or extract this repository to a writable directory.
2. Start the launcher:

   **Windows (PowerShell or CMD):**
   ```powershell
   .\launch.bat
   ```

   **macOS/Linux:**
   ```bash
   bash launch.sh
   ```

3. On first launch, setup downloads the runtimes and Hermes source and prepares an isolated environment. An internet connection and several hundred megabytes of free space are needed for setup.
4. Follow Hermes setup to configure a provider and API key.

Setup flags and other launcher options are documented in [`scripts/COMMANDS.md`](scripts/COMMANDS.md).

## Launcher commands

The portable wrappers support direct subcommands that execute without starting the interactive dashboard:

| Windows | macOS/Linux | Description |
| --- | --- | --- |
| `.\launch.bat diagnostics` | `bash launch.sh diagnostics` | Inspect platform, runtimes, virtualenv, source, and dependencies (read-only) |
| `.\launch.bat upgrade preview` | `bash launch.sh upgrade preview` | Preview planned updates to source and runtimes before applying |
| `.\launch.bat upgrade` | `bash launch.sh upgrade` | Back up metadata and apply update with automatic rollback on error |
| `.\launch.bat rollback` | `bash launch.sh rollback` | Revert to the snapshot created before the last upgrade |
| `.\launch.bat backup [--dest <path>]` | `bash launch.sh backup [--dest <path>]` | Create verified backup of `data/` preserving relative paths |
| `.\launch.bat restore <file>` | `bash launch.sh restore <file>` | Verify integrity and restore user data (conflict-safe; preview with `--dry-run`) |
| `.\launch.bat prune --keep 5` | `bash launch.sh prune --keep 5` | Apply backup retention (keep N newest; preview with `--dry-run`) |
| `.\launch.bat sync --dry-run` | `bash launch.sh sync --dry-run` | Sync `data/` to S3 / compatible / local provider (preview first) |
| `.\launch.bat schedule status` | `bash launch.sh schedule status` | Opt-in scheduled backup/sync (`enable`, `pause`, `resume`, `disable`, `run-now`, `check`) |
| `.\launch.bat profile <cmd>` | `bash launch.sh profile <cmd>` | Manage profiles (`list`, `create`, `delete`) |
| `.\launch.bat mcp <cmd>` | `bash launch.sh mcp <cmd>` | Manage MCP servers |
| `.\launch.bat hermes <cmd>` | `bash launch.sh hermes <cmd>` | Forward command directly to the Hermes CLI |

## Diagnostics

Run diagnostics to check platform compatibility, installed runtime binaries, virtual environment, and optional tools without altering any files:

```bash
# Windows
.\launch.bat diagnostics

# macOS / Linux
bash launch.sh diagnostics

# Machine-readable JSON output
python tools/doctor/diagnostics.py --json
```

## Backup, restore, and security limitations

Create backups of your user data with cryptographic verification:

```bash
# Create a verified archive (default destination: .cache/backups/)
python tools/backup/backup_manager.py backup

# Specify a custom destination archive or directory
python tools/backup/backup_manager.py backup --destination D:\HermesBackups\backup.zip

# Verify an existing backup archive without altering files
python tools/backup/backup_manager.py verify D:\HermesBackups\backup.zip

# Restore and verify files to data/ (safe default: aborts on conflicts; preview first)
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --dry-run
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --overwrite-policy skip
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --overwrite-policy keep-both

# Retention: preview then apply (keep newest 5)
python tools/backup/backup_manager.py prune --dry-run --keep 5
python tools/backup/backup_manager.py prune --keep 5
```

Scheduled backups/sync are strictly opt-in (disabled until you enable them).
Every preview explains what data is uploaded; `pause`/`resume`/`disable` stop
automatic runs; passphrases are never stored:

```bash
python tools/sync/schedule_manager.py status
python tools/sync/schedule_manager.py enable --interval-hours 24 --mode backup --retention-keep 5
python tools/sync/schedule_manager.py enable --interval-hours 12 --mode s3 --bucket my-bucket --prefix hermes/ --encrypt --no-overwrite
python tools/sync/schedule_manager.py run-now --dry-run
python tools/sync/schedule_manager.py pause
python tools/sync/schedule_manager.py resume
python tools/sync/schedule_manager.py disable
```

S3 sync protects existing remote data (`--no-overwrite` / `--conflict-policy
fail|skip|overwrite|keep-both`), supports `--verify` size checks, remote
retention (`--retention-keep N` + `--prune`), and additional providers
(`--provider s3|s3-compatible|minio|wasabi|spaces|b2|r2|local`; S3-compatible
targets require `--endpoint-url` and a `--dry-run` first — see
`tools/sync/providers.py`):

```bash
python tools/sync/s3_sync.py --bucket my-bucket --prefix hermes/ --dry-run
python tools/sync/s3_sync.py --bucket my-bucket --prefix hermes/ --no-overwrite --verify
python tools/sync/s3_sync.py --bucket ignored --provider local --local-dir D:\Mirror --dry-run
```

> [!WARNING]
> **Encryption & Password Recovery Limitations:**
> - Vault files encrypted with DataVault are backed up in their encrypted ciphertext envelope.
> - Encryption keys are derived using PBKDF2-HMAC-SHA256 from your passphrase.
> - **There is NO backdoor, master key, or recovery question.**
> - Restoring a backup does NOT reset or bypass vault passwords.
> - If you lose your vault passphrase, encrypted data is permanently unrecoverable.

## Upgrades and rollback

Before upgrading, preview changes to see what components will be updated:

```bash
python tools/upgrade/upgrade_manager.py preview
```

Applying an upgrade automatically creates a metadata snapshot in `.cache/backups/upgrade_<timestamp>/` preserving `manifest.json`, the source git commit, and virtualenv state. If the upgrade fails or you need to revert:

```bash
# Automatic rollback to previous snapshot
python tools/upgrade/upgrade_manager.py rollback

# Or run via launcher
.\launch.bat rollback
bash launch.sh rollback
```

## Data and runtime locations

| Path | Purpose |
| --- | --- |
| `data/` | User settings, credentials, profiles, sessions, and other persistent data |
| `src/hermes-agent/` | Hermes source checkout downloaded by setup |
| `src/security/` | This repository’s vault and token utilities |
| `.cache/runtimes/` | Downloaded platform runtimes and the prepared environment |
| `.cache/backups/` | Upgrade snapshots and user data backups |
| `.cache/logs/` | Launcher and setup logs |

Back up `data/` regularly. Do not store unencrypted backups or credentials in a public or shared location.

## Vault encryption

The optional security CLI protects selected files in `data/` using password-derived Fernet encryption. It uses PBKDF2-HMAC-SHA256 with a random salt per file. Encrypted content is stored as a JSON envelope in place of the plaintext content; filenames are not changed. Keep a secure backup of your password and test recovery before relying on encryption.

The YubiKey utilities can report device availability and guide PIN setup. **YubiKey detection is not currently used to derive or replace the vault password**, and setting the vault’s hardware-token flag does not make password-based vault encryption passwordless.

See [`SECURITY.md`](SECURITY.md) for the accurate workflow, limitations, and recovery guidance.

## Optional tools

- **Electron launcher:** see [`UX_MANAGEMENT.md`](UX_MANAGEMENT.md).
- **Health report:** `tools/doctor/export_health.py` writes a JSON report for the dashboard.
- **S3 sync:** `tools/sync/s3_sync.py` can upload the data directory, optionally encrypting each uploaded file.
- **Profiles and MCP:** see [`scripts/COMMANDS.md`](scripts/COMMANDS.md) and the corresponding utilities under `tools/`.

## Documentation

- [Command reference](scripts/COMMANDS.md) — launcher, setup, reset, diagnostics, upgrade, and backup usage
- [Security guide](SECURITY.md) — vault encryption and YubiKey limitations
- [Security quick reference](SECURITY_QUICKREF.md) — common vault commands
- [UX and management tools](UX_MANAGEMENT.md) — GUI, health reports, profiles, and S3
- [Implementation summary](IMPLEMENTATION_SUMMARY.md) — project components and repaired integration issues
- [Contributing](Contributing.md) — contribution workflow
- [Code of conduct](CODE_OF_CONDUCT.md) — community expectations

## Contributing

Contributions are welcome. Please read [`Contributing.md`](Contributing.md) and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

See [`license`](license) for the project license.
