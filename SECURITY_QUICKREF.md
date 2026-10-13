# Vault Security Quick Reference

## Commands

The security package lives under `src/`. From the repository root, set Python’s module path before running it.

**macOS/Linux**
```bash
PYTHONPATH=src python -m security encrypt data/
PYTHONPATH=src python -m security status data/
PYTHONPATH=src python -m security decrypt data/
```

**Windows PowerShell**
```powershell
$env:PYTHONPATH = "$PWD\src"
python -m security encrypt data\
python -m security status data\
python -m security decrypt data\
```

Encryption prompts for a new password twice. Decryption prompts for the existing password. Use the launcher to start Hermes; it checks whether the selected profile’s vault needs to be unlocked.

## What the vault protects

- Root-level `.env`, `config.yaml`, `config.yml`, and `soul.md`.
- Files beneath `sessions/`, `memory/`, and `logs/`.

Encryption replaces selected file contents in place with JSON envelopes. Filenames are unchanged. Other data files are not automatically encrypted.

## Key facts

- Fernet encryption with PBKDF2-HMAC-SHA256 (100,000 iterations).
- A fresh 16-byte random salt is used per file.
- The `.vault` file stores status metadata, not a recoverable key.
- The YubiKey option is informational metadata only today; the vault remains password-based.
- A forgotten password cannot be reset. Keep and test a separate backup.

See [`SECURITY.md`](SECURITY.md) for scope, setup, recovery, and known limitations.
