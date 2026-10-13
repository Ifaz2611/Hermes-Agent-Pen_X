# Security and Vault Guide

This guide documents the security utilities included in Hermes Agent Pendrive_X. Vault encryption is optional; it does not replace operating-system security, secure backups, or careful credential handling.

## Current capabilities

- Password-based encryption and decryption of selected files in a data directory.
- Vault status reporting.
- YubiKey availability/status checks and a helper that invokes YubiKey PIN setup.
- Automatic vault-unlock helpers used by the platform launchers.

**Important YubiKey limitation:** YubiKey is not currently part of the vault key derivation or unlock flow. The `--hardware-token` option records a setting in `.vault`; it does not make vault access passwordless or require a YubiKey. Do not treat the token flag as an additional cryptographic factor.

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
```

Encryption prompts for a password and confirmation if `--password` is omitted; the interactive prompt requires at least eight characters. Decryption prompts for the existing password if `--password` is omitted. Prefer interactive prompts over putting passwords in command arguments, which can expose them in shell history or process listings. Use a strong, unique password.

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
2. Store encrypted backups separately from the encryption password.
3. Test decryption from a backup before depending on it.
4. Do not sync plaintext credentials to an untrusted destination.

If you forget the password, the encrypted files cannot be recovered by this project. Restore from a known-good backup. Do not delete encrypted data until a restored copy has been verified.

The S3 utility can encrypt files before uploading, but it does not provide key management or recovery. Review its options and destination before use; AWS credentials should come from a protected AWS profile or the standard AWS credential provider chain, not from source code.

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
