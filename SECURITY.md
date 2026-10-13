# Security and Vault Guide

This guide documents the security utilities included in Hermes Agent Pendrive_X. Vault encryption is optional; it does not replace operating-system security, secure backups, or careful credential handling.

## Current capabilities

- Password-based encryption and decryption of selected files in a data directory.
- Atomic file writes and transactional backups to protect against corruption during lock/unlock.
- Safe rollback on operation failure and automatic recovery for interrupted updates.
- Vault status and pending recovery reporting.
- Diagnostic YubiKey availability/status checks and PIN setup helper (independent of vault).
- Automatic vault-unlock helpers used by the platform launchers.

**YubiKey and hardware tokens:** The vault is strictly password-based. YubiKey and hardware-token utilities are standalone diagnostics only (`python -m security token` / `yubikey`); they are NOT used in vault key derivation and do not provide passwordless unlocking. Misleading hardware-token metadata flags have been removed from the vault CLI. Do not advertise or assume passwordless vault unlocking.

## What is encrypted

When you lock a vault, the security module processes matching files:

- Root-level `.env`, `config.yaml`, `config.yml`, and `soul.md` (case-insensitive name match).
- Files beneath `sessions/`, `memory/`, and `logs/`.

The content is replaced in place by a UTF-8 JSON envelope containing the salt and Fernet token. The original filename remains unchanged. The `.vault` metadata file is not itself encrypted. Files outside the listed names and directories are not automatically protected.

Before encrypting, make a backup and confirm that the data directory contains only the files you intend to protect. Never run tests against your only copy of important data.

## Requirements

The security module is under `src/security/`. For direct use from the repository root, make `src/` available on Python’s module path.

**macOS/Linux:**
```bash
PYTHONPATH=src python -m security --help
```

**Windows PowerShell:**
```powershell
$env:PYTHONPATH = "$PWD\src"
python -m security --help
```

The `cryptography` package is required for encryption and decryption. YubiKey detection additionally needs `ykman` (provided by YubiKey Manager). The project setup scripts install the portable runtime dependencies.

## Encrypt, inspect, and decrypt

Run commands from the repository root after setting `PYTHONPATH` as above:

```text
python -m security encrypt data/
python -m security status data/
python -m security decrypt data/
python -m security recover data/
```

Encryption prompts for a password and confirmation if `--password` is omitted; the interactive prompt requires at least eight characters. Decryption prompts for the existing password if `--password` is omitted. You may also specify the password via the `HERMES_VAULT_PASSWORD` environment variable. Avoid passing passwords directly in `--password` command arguments to prevent exposing them in shell history, process listings, or logs. Use a strong, unique password.

All lock and unlock operations are atomic and transactional. A backup is staged in `.vault_backup` during an active operation and cleared upon success. If an error occurs, the vault rolls back immediately. If the process is killed partway through, run `python -m security recover data/` to restore the pre-operation state cleanly.

The launchers check the selected data directory and invoke the unlock helper when the vault metadata indicates that it is locked. Keep an independent backup of the password: there is no password reset or recovery mechanism.

## Cryptographic format

- **Encryption:** Fernet authenticated symmetric encryption.
- **Key derivation:** PBKDF2-HMAC-SHA256, 100,000 iterations.
- **Salt:** 16 random bytes per encrypted file.
- **Envelope:** JSON containing a marker, version, salt, token, and original filename.

Encrypted files keep their original names and are written in place. Do not assume a `.enc` extension is created by the vault CLI.

## YubiKey utilities

Check device detection and status:

```text
python -m security token status
python -m security yubikey setup --mode fido2 --setup-pin
```

Supported mode labels are `otp`, `fido2`, and `piv`. Device detection depends on the `ykman` command being available. The PIN helper delegates to YubiKey Manager; verify its output and device configuration yourself. These utilities do not currently bind the YubiKey to vault encryption.

## Backups and recovery

1. Keep at least one separate backup of important data.
2. Use the backup tool (`python tools/backup/backup_manager.py backup` or `launch.bat backup` / `launch.sh backup`) to produce verified archives with relative path preservation and SHA-256 manifests.
3. Verify backups before relying on them: `python tools/backup/backup_manager.py verify <backup-file>`.
4. Store encrypted backups separately from the encryption password.
5. Test decryption from a backup before depending on it.
6. Do not sync plaintext credentials to an untrusted destination.

> [!WARNING]
> **Password Recovery Limitation:** If you forget or lose the password, encrypted files CANNOT be recovered by this project or anyone else. There is NO master key, backdoor, or recovery question. Restoring a backup does NOT reset the vault password. Do not delete encrypted data until a restored copy has been verified.

The S3 utility (`tools/sync/s3_sync.py`) can encrypt files before uploading. It supports offline dry runs (`--dry-run`) without requiring AWS credentials or network access. Encryption passwords can be passed securely via `HERMES_VAULT_PASSWORD`, `HERMES_S3_PASSWORD`, or `S3_SYNC_PASSWORD`. Any individual file encryption or upload failures are tracked and reported with a non-zero exit code. AWS credentials should come from the standard AWS credential chain (environment variables or `~/.aws/credentials`), never from command arguments or source code.

## Troubleshooting

| Problem | Check |
| --- | --- |
| `No module named security` | Set `PYTHONPATH` to this repository’s `src/` directory. |
| Missing `cryptography` | Install project dependencies or run the platform setup script. |
| Unlock fails | Check the password and make a backup copy of the encrypted files before retrying. |
| YubiKey not detected | Confirm `ykman` is installed, connect the device, and run `ykman list`. |
| Permission error | Confirm the data directory is writable and not locked by another process. |

## Reporting a vulnerability

Do not publish exploitable details in a public issue. Contact the repository maintainers through a private security channel listed in the repository settings or project site. Include the affected component, impact, and safe reproduction steps; do not include real credentials or private user data.
