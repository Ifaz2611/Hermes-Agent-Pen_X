# Hermes Agent Pendrive_X

Hermes Agent Pendrive_X is a portable launcher for the [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent). It keeps the Hermes checkout, runtimes, and portable user data under this project directory so you can run it from a local folder or removable drive.

## What’s included

- Windows and macOS/Linux launchers with first-run runtime setup.
- An isolated runtime cache and Hermes virtual environment.
- Persistent user data in `data/`.
- Optional password-based encryption for selected files in the data vault.
- Utilities for profiles, health reports, MCP configuration, and optional S3 uploads.
- A small optional Electron launcher.

## Quick start

1. Clone or extract this repository to a writable directory.
2. Start the launcher:

   **Windows (PowerShell):**
   ```powershell
   .\launch.bat
   ```

   **macOS/Linux:**
   ```bash
   bash launch.sh
   ```

3. On first launch, setup downloads the runtimes and Hermes source and prepares an isolated environment. An internet connection and several hundred megabytes of free space are needed for setup.
4. Follow Hermes setup to configure a provider and API key.

The setup scripts currently target Python 3.11 and Node.js 22. Setup flags and other launcher options are documented in [`scripts/COMMANDS.md`](scripts/COMMANDS.md).

## Data and runtime locations

| Path | Purpose |
| --- | --- |
| `data/` | User settings, credentials, profiles, sessions, and other persistent data |
| `src/hermes-agent/` | Hermes source checkout downloaded by setup |
| `src/security/` | This repository’s vault and token utilities |
| `.cache/runtimes/` | Downloaded platform runtimes and the prepared environment |
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

- [Command reference](scripts/COMMANDS.md) — launcher, setup, reset, and utility usage
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
