# Command Reference

This guide covers the portable launchers and repository utilities. Hermes CLI subcommands are supplied by the downloaded Hermes source and may vary by version; use `hermes --help` for the commands supported by the installed version.

## Start Hermes

| Platform | Command |
| --- | --- |
| Windows | `.\launch.bat` |
| macOS/Linux | `bash launch.sh` |

Direct launcher commands:

| Windows | macOS/Linux | Description |
| --- | --- | --- |
| `.\launch.bat --help` | `bash launch.sh --help` | Show launcher help message and options |
| `.\launch.bat --version` | `bash launch.sh --version` | Print launcher and Hermes versions |
| `.\launch.bat diagnostics` | `bash launch.sh diagnostics` | Run read-only wrapper diagnostics |
| `.\launch.bat upgrade preview` | `bash launch.sh upgrade preview` | Preview planned updates to Hermes source and runtimes |
| `.\launch.bat upgrade` | `bash launch.sh upgrade` | Back up metadata and apply update with rollback recovery |
| `.\launch.bat rollback` | `bash launch.sh rollback` | Restore system state to previous upgrade snapshot |
| `.\launch.bat backup` | `bash launch.sh backup` | Create verified backup of `data/` preserving relative paths |
| `.\launch.bat restore <file>` | `bash launch.sh restore <file>` | Verify integrity and restore user data (conflict-safe; `--dry-run`, `--overwrite-policy`) |
| `.\launch.bat prune` | `bash launch.sh prune` | Apply backup retention (`--keep N`, `--dry-run` preview) |
| `.\launch.bat sync` | `bash launch.sh sync` | Sync `data/` to S3 / compatible / local provider (`--dry-run` first) |
| `.\launch.bat schedule <cmd>` | `bash launch.sh schedule <cmd>` | Opt-in scheduled backup/sync (`status`, `enable`, `pause`, `resume`, `disable`, `run-now`, `check`) |
| `.\launch.bat profile <cmd>` | `bash launch.sh profile <cmd>` | Manage profiles (`list`, `create`, `switch`, `delete`) |
| `.\launch.bat mcp <cmd>` | `bash launch.sh mcp <cmd>` | Manage MCP servers without booting runtime |
| `.\launch.bat hermes <cmd>` | `bash launch.sh hermes <cmd>` | Forward command to Hermes without opening dashboard |

Launcher options `-h`, `--help`, `/help`, `/?`, `-v`, `--version` exit immediately with documentation. Standalone subcommands (`diagnostics`, `upgrade`, `rollback`, `backup`, `restore`, `profile`, `mcp`) dispatch directly without requiring runtime extraction or venv reconstruction.

## Wrapper diagnostics

The diagnostics command checks host platform compatibility, runtime versions, virtual environment, source checkout, data path, and optional dependencies strictly without modifying user data.

```bash
# Windows
.\launch.bat diagnostics

# macOS / Linux
bash launch.sh diagnostics

# Direct invocation with machine-readable JSON
python tools/doctor/diagnostics.py --json
```

Checks conducted:
1. **Platform**: OS, architecture, supported status (Windows x64, Linux x64/arm64, macOS x64/arm64).
2. **Runtime versions**: Python (>=3.11), Node.js (>=22), uv, ripgrep, Git, and manifest validation.
3. **Virtual environment**: Venv folder, Python binary, activation scripts, `pyvenv.cfg`.
4. **Source checkout**: `src/hermes-agent`, git status or version, and `src/security` package.
5. **Data path**: Read/write access (checked non-destructively), `.env`, `config.yaml`, and vault file count.
6. **Optional dependencies**: `cryptography`, `yubikey-manager` (`ykman`), Playwright, Telegram bot, boto3, and Electron GUI.

## Upgrades and rollback

Upgrades inspect the current checkout and manifest, explain changes before applying them, back up metadata to `.cache/backups/upgrade_<timestamp>/`, and provide an automatic rollback path if an update fails.

```bash
# 1. Preview changes (read-only, no modifications)
python tools/upgrade/upgrade_manager.py preview
# Or via launcher:
.\launch.bat upgrade preview
bash launch.sh upgrade preview

# 2. Apply upgrade with confirmation and automatic backup
python tools/upgrade/upgrade_manager.py apply
# Or via launcher:
.\launch.bat upgrade
bash launch.sh upgrade

# 3. Roll back to previous snapshot
python tools/upgrade/upgrade_manager.py rollback
# Or via launcher:
.\launch.bat rollback
bash launch.sh rollback
```

### Documented recovery path

If an update fails mid-way:
1. The pre-upgrade metadata snapshot is preserved in `.cache/backups/upgrade_<timestamp>/` with `manifest.json`, `source_state.json`, and `rollback_descriptor.json`.
2. Automatic rollback restores the original manifest and source commit via `launch.bat rollback` or `launch.sh rollback`.
3. Manual recovery:
   - Revert source: `cd src/hermes-agent && git checkout <previous_commit>`
   - Restore manifest: `copy .cache\backups\upgrade_<ts>\manifest.json .cache\runtimes\<platform>\manifest.json`
   - Re-sync virtualenv: run `.\scripts\setup-windows.ps1` or `bash scripts/setup-unix.sh`.

## Backup and restore workflow

The backup manager creates cryptographic SHA-256 archives of user data preserving relative paths, verifies restored files, and alerts users to encryption limitations.

```bash
# Create verified backup (default: .cache/backups/hermes_backup_<timestamp>.zip)
python tools/backup/backup_manager.py backup

# Specify custom destination (.zip archive or folder)
python tools/backup/backup_manager.py backup --destination D:\Backups\hermes_data.zip
python tools/backup/backup_manager.py backup --destination D:\Backups\folder\

# Verify backup archive integrity against embedded manifest
python tools/backup/backup_manager.py verify D:\Backups\hermes_data.zip

# Restore and verify files to data/ (default --overwrite-policy fail: aborts on conflicts)
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip

# Preview restore without modifying files (shows CREATE vs CONFLICT)
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --dry-run

# Conflict policies: skip (preserve existing), overwrite (explicit), keep-both (sidecar)
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --overwrite-policy skip
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --overwrite-policy keep-both
python tools/backup/backup_manager.py restore D:\Backups\hermes_data.zip --overwrite

# Retention: preview then apply (keep newest 5 in .cache/backups/)
python tools/backup/backup_manager.py prune --dry-run --keep 5
python tools/backup/backup_manager.py prune --keep 5
```

## Scheduled backup/sync (opt-in)

Schedules are disabled until you opt in. Status and previews always explain what
data is uploaded (source dir, file count, bytes, encrypted count, destination).
`pause`/`resume`/`disable` provide clear stop controls. Passphrases are never
stored — they come from `HERMES_VAULT_PASSWORD` at run time.

```bash
python tools/sync/schedule_manager.py status
python tools/sync/schedule_manager.py enable --interval-hours 24 --mode backup --retention-keep 5
python tools/sync/schedule_manager.py enable --interval-hours 12 --mode s3 --bucket my-bucket --prefix hermes/ --encrypt --no-overwrite
python tools/sync/schedule_manager.py run-now --dry-run
python tools/sync/schedule_manager.py check --run-if-due
python tools/sync/schedule_manager.py pause
python tools/sync/schedule_manager.py resume
python tools/sync/schedule_manager.py disable
```

### Encryption and password recovery limitations

> [!WARNING]
> - Vault files encrypted with DataVault are backed up in their encrypted ciphertext form.
> - Encryption keys are derived using PBKDF2-HMAC-SHA256 from your passphrase.
> - **There is NO backdoor, master key, password reset, or escrow service.**
> - Restoring a backup does NOT reset or change vault passwords.
> - If you forget or lose your vault password, data in encrypted files is permanently unrecoverable.

## Runtime setup

Setup runs automatically on first launch or can be invoked directly:

**Windows PowerShell**
```powershell
.\scripts\setup-windows.ps1 -Root $PWD.Path
```

**macOS/Linux**
```bash
bash scripts/setup-unix.sh "$PWD"
```

All downloaded runtime archives are cryptographically verified against SHA-256 checksums in [`manifests/runtimes.json`](manifests/runtimes.json).

Supported options:
- Windows: `-SkipGit`, `-SkipPlaywright`, `-SkipUv`, `-DryRun`, `-Launch`.
- Unix: `--skip-uv`, `--skip-rg`, `--skip-playwright`, `--dry-run`.

## Supported runtime versions

| Component | Target Version | Source / Asset |
| --- | --- | --- |
| Python | `3.11.10+20241016` | python-build-standalone (Astral) |
| Node.js | `22.14.0` LTS | Node.js official binaries |
| uv | `0.6.8` | Astral uv standalone |
| ripgrep | `14.1.1` | BurntSushi ripgrep standalone |
| Git (Windows) | `2.53.0.windows.1` | MinGit 64-bit |

## CI & repository integrity checks

Run all syntax validations, markdown link checks, and git tracking hygiene locally:

```bash
python scripts/ci_check.py
```

Checks shell (`bash -n`), PowerShell (`AST parser`), Python (`py_compile`), JavaScript (`node --check`), markdown relative links, and verifies that generated files, runtime downloads, and local secrets are never tracked in Git.

## Security CLI

The security package is located in `src/security/`. Direct invocation requires adding `src/` to Python’s module path. See [`../SECURITY.md`](../SECURITY.md) for password handling and security limitations.

**macOS/Linux**
```bash
PYTHONPATH=src python -m security --help
PYTHONPATH=src python -m security status data/
```

**Windows PowerShell**
```powershell
$env:PYTHONPATH = "$PWD\src"
python -m security --help
python -m security status data\
```

## Repository utilities

### Profiles

```bash
python tools/profiles/profile_manager.py list
python tools/profiles/profile_manager.py create <name>
python tools/profiles/profile_manager.py delete <name>
```

### Health report

```bash
python tools/doctor/export_health.py
python tools/doctor/export_health.py --data-dir path\to\data --out path\to\health.json
```

The default report is written to `data/health.json`.

### MCP manager

```bash
python tools/mcp/mcp_manager.py list
python tools/mcp/mcp_manager.py available
python tools/mcp/mcp_manager.py install filesystem
python tools/mcp/mcp_manager.py add <name> --cmd <command> --env KEY=VALUE --args <arg>...
python tools/mcp/mcp_manager.py remove <name>
```

### S3 sync (with conflict protection, verification, retention, providers)

```bash
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --dry-run
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --encrypt --dry-run
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --encrypt
# Never silently overwrite remote data:
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --no-overwrite
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --conflict-policy fail
# Verify uploads + remote retention (preview unless --prune):
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --verify
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --retention-keep 5
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --retention-keep 5 --prune
# Additional providers (only after S3 is reliable; always --dry-run first):
python tools/sync/s3_sync.py --bucket <bucket> --provider s3-compatible --endpoint-url https://s3.example.com --dry-run
python tools/sync/s3_sync.py --bucket ignored --provider local --local-dir D:\Mirror --dry-run
```

See `tools/sync/providers.py` for the provider matrix (`s3`, `s3-compatible`,
`minio`, `wasabi`, `spaces`, `b2`, `r2`, `local`).

## Reset scripts

Reset scripts can preview actions safely using dry-run flags (`-DryRun` / `--dry-run`), or execute soft/full resets. Back up `data/` before running full resets.

**Windows PowerShell**
```powershell
.\scripts\reset-windows.ps1 -Mode soft -DryRun
.\scripts\reset-windows.ps1 -Mode full -DryRun
.\scripts\reset-windows.ps1 -Mode soft
.\scripts\reset-windows.ps1 -Mode full
```

**macOS/Linux**
```bash
bash scripts/reset-unix.sh soft --dry-run
bash scripts/reset-unix.sh full --dry-run
bash scripts/reset-unix.sh soft
bash scripts/reset-unix.sh full
```
