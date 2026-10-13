# User Interface and Management Tools

This document covers the optional desktop UI and the repository’s management utilities.

## Electron launcher

The Electron app is in `gui/electron/`. It can start the portable launcher, open the `data/` directory, and open a health dashboard window.

```bash
cd gui/electron
npm install
npm start
```

The health action runs `tools/doctor/export_health.py` and loads the dashboard. The exporter writes `data/health.json` by default. The report includes an actionable `health_checks` checklist (missing runtimes, setup state, vault state, log findings with fix hints), runtime/manifest status, setup configuration, vault messages including pending-recovery warnings, and tailed excerpts of gateway/launch/setup logs with error lines surfaced first. The dashboard renders these checks as a status table plus runtime, vault, and log sections, with an offline-safe storage table when charts cannot load. The report can include local paths, Python version, vault status, log excerpts, and optional API-cost data; review the output before sharing it.

## Health report

Run the exporter from the repository root:

```bash
python tools/doctor/export_health.py
```

Choose another data directory or output file with:

```bash
python tools/doctor/export_health.py --data-dir path\to\data --out path\to\health.json
```

On macOS/Linux, use `/` in paths. The tool collects local filesystem and environment information; it does not contact a remote health service.

## Profiles

Profiles are stored under `data/profiles/`. The profile manager supports listing, creating, and deleting profiles:

```bash
python tools/profiles/profile_manager.py list
python tools/profiles/profile_manager.py list --json
python tools/profiles/profile_manager.py create <name>
python tools/profiles/profile_manager.py delete <name>
```

The Electron launcher exposes the same workflow: a profile selector (switch persists to `data/active-profile.json` and is used for the next launch), a create field with name validation, and a two-step delete confirmation (acknowledgement checkbox plus re-typing the exact profile name). The CLI validates names before any filesystem change; the UI additionally blocks deletion until both confirmation steps pass.

The launcher supports selecting a profile: `launch.bat /profile <name>` on Windows and `bash launch.sh --profile <name>` on macOS/Linux. A profile may contain credentials and settings, so apply the same protection and backup practices as for `data/`.

## Accessibility and first-run behavior

The launcher and dashboard windows support full keyboard navigation (Tab/Shift-Tab, Enter/Space, Esc closes the delete dialog), always-visible focus outlines, `role="status"`/`role="alert"` live regions for readable error messages, and a persisted high-contrast theme (also honoring the OS `prefers-contrast` setting).

First-run setup reports staged progress to `setup-progress.json` (python → node → uv → ripgrep → source → venv → deps → browsers) and tails `setup.log`/`install.log`. Cancellation (Ctrl-C, the UI Cancel button, or a failed stage) preserves all logs, removes any partial `ready.flag`, and writes `setup-cancelled.flag`, so the next launch simply resumes — check the setup section of the launcher or the dashboard for the recoverable-state message.

## S3 sync

The optional uploader is `tools/sync/s3_sync.py`. It requires `boto3` and AWS credentials configured through the normal AWS credential chain or an AWS profile.

```bash
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --dry-run
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --encrypt --password <passphrase>
```

The script recursively considers files in the selected data directory. With `--encrypt`, it stages an encrypted copy per file and uploads the encrypted form. The passphrase option is supplied on the command line, so avoid shared hosts and shell histories that expose process arguments. Review the destination, file selection, AWS permissions, and passphrase handling before uploading.

## MCP and maintenance commands

See [`scripts/COMMANDS.md`](scripts/COMMANDS.md) for the launcher, setup scripts, reset scripts, and MCP utility command references.
