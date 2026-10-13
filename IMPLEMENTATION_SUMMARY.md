# Implementation and Maintenance Summary

This document describes the current structure of Hermes Agent Pendrive_X and records the integration issues addressed in the portable launcher and supporting tools. It is a project-maintenance note, not a security certification or a substitute for testing the current checkout.

## Project components

| Component | Location | Responsibility |
| --- | --- | --- |
| Windows launcher | `launch.bat` | Runtime setup, profile selection, and Hermes startup |
| macOS/Linux launcher | `launch.sh` | Platform-aware setup, environment preparation, and Hermes startup |
| Runtime setup | `scripts/setup-windows.ps1`, `scripts/setup-unix.sh` | Download runtimes and Hermes source; create the isolated environment |
| Vault CLI and library | `src/security/` | Password-based encryption, decryption, status, and token utilities |
| Vault unlock helpers | `scripts/unlock-vault.ps1`, `scripts/unlock-vault.sh` | Unlock encrypted profile data during launcher startup |
| Health exporter | `tools/doctor/export_health.py` | Write a JSON health report for the GUI |
| S3 utility | `tools/sync/s3_sync.py` | Upload files from the data directory, with optional per-file encryption |
| Profile manager | `tools/profiles/profile_manager.py` | Manage profile data beneath `data/profiles/` |
| MCP manager | `tools/mcp/mcp_manager.py` | Configure and manage MCP server entries |
| Electron UI | `gui/electron/` | Launch Hermes, open the data folder, and show a health dashboard |

## Integration repairs

The project received a cross-platform integration pass covering these areas:

- Restored the missing `src/security/` package used by launchers and utilities, and adjusted ignore rules so the package is tracked without exposing the downloaded Hermes checkout.
- Reworked launcher argument handling, startup flow, platform/runtime selection, and environment handling on Windows and macOS/Linux.
- Corrected setup-script runtime metadata, platform-specific download selection, virtual-environment reuse, dry-run behavior, and Windows extraction fallbacks.
- Fixed repository-root resolution in health, S3, and profile tools so they do not depend on the caller’s working directory.
- Corrected MCP argument parsing and option handling.
- Updated the Electron app to resolve project paths from its own location and launch the platform-appropriate script.
- Corrected reset and vault-unlock error handling and improved portability for macOS shell utilities.
- Added UTF-8 BOMs to PowerShell scripts for compatibility with Windows PowerShell 5.1.

These notes summarize intended repairs; verify the current scripts and test them on each target OS before release.

## Security behavior to understand

- Vault operations use Fernet envelopes and PBKDF2-HMAC-SHA256 key derivation with 100,000 iterations and a 16-byte random salt for each encrypted file.
- Selected sensitive files and contents under `sessions/`, `memory/`, and `logs/` are encrypted in place. File names remain the same; encrypted files contain a JSON envelope.
- The `.vault` file records vault status. It is not a copy of the encryption key and cannot recover a forgotten password.
- YubiKey functions currently provide device detection/status and a PIN-setup helper. Vault encryption and decryption still require the password; the hardware-token option records configuration metadata and does not provide passwordless cryptographic protection.
- S3 encryption creates encrypted staging files for upload. Check the selected data directory and AWS destination before syncing.

See [`SECURITY.md`](SECURITY.md) for operational details and limitations.

## Local validation

Run validation from the repository root using the tools available on the target platform. At minimum, check shell syntax, parse PowerShell scripts on Windows, run the security CLI’s help/status commands, and smoke-test setup, unlock, and launcher argument forwarding without using real credentials or production data.
