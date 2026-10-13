# Vault Security Quick Reference

## Commands

The security package lives under `src/`. From the repository root, set Python’s module path before running it.

**macOS/Linux**
```bash
PYTHONPATH=src python -m security encrypt data/
PYTHONPATH=src python -m security status data/
PYTHONPATH=src python -m security decrypt data/
PYTHONPATH=src python -m security recover data/
```

**Windows PowerShell**
```powershell
$env:PYTHONPATH = "$PWD\src"
python -m security encrypt data\
python -m security status data\
python -m security decrypt data\
python -m security recover data\
```

Encryption prompts for a new password twice. Decryption prompts for the existing password. Alternatively, set the `HERMES_VAULT_PASSWORD` environment variable to avoid passing passwords via interactive prompts or CLI arguments. Use the launcher to start Hermes; it checks whether the selected profile’s vault needs to be unlocked.

## What the vault protects

- Root-level `.env`, `config.yaml`, `config.yml`, and `soul.md`.
- Files beneath `sessions/`, `memory/`, and `logs/`.

Vault updates are transactional and atomic: updates write to temporary files before atomic replacement, and operation backups are maintained in `.vault_backup` so interrupted operations can be restored with `python -m security recover <dir>`.

## Key facts

- Fernet encryption with PBKDF2-HMAC-SHA256 (100,000 iterations).
- A fresh 16-byte random salt is used per file.
- Atomic file writes and transactional backups prevent partial state corruption.
- The `.vault` file stores status metadata, not a recoverable key.
- The vault is strictly password-based; hardware-token options have been removed from vault unlocking to avoid misleading passwordless claims.
- A forgotten password cannot be reset. Keep and test a separate backup.

See [`SECURITY.md`](SECURITY.md) for scope, setup, recovery, and known limitations.
