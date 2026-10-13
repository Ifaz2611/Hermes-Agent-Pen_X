# User Interface and Management Tools

This document covers the optional desktop UI and the repository’s management utilities.

## Electron launcher

The Electron app is in `gui/electron/`. It can start the portable launcher, open the `data/` directory, and open a health dashboard window.

```bash
cd gui/electron
npm install
npm start
```

The health action runs `tools/doctor/export_health.py` and loads the dashboard. The exporter writes `data/health.json` by default. The report can include local paths, Python version, vault status, log excerpts, and optional API-cost data; review the output before sharing it.

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
python tools/profiles/profile_manager.py create <name>
python tools/profiles/profile_manager.py delete <name>
```

The launcher supports selecting a profile: `launch.bat /profile <name>` on Windows and `bash launch.sh --profile <name>` on macOS/Linux. A profile may contain credentials and settings, so apply the same protection and backup practices as for `data/`.

## S3 sync

The optional uploader is `tools/sync/s3_sync.py`. It requires `boto3` and AWS credentials configured through the normal AWS credential chain or an AWS profile.

```bash
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --dry-run
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --encrypt --password <passphrase>
```

The script recursively considers files in the selected data directory. With `--encrypt`, it stages an encrypted copy per file and uploads the encrypted form. The passphrase option is supplied on the command line, so avoid shared hosts and shell histories that expose process arguments. Review the destination, file selection, AWS permissions, and passphrase handling before uploading.

## MCP and maintenance commands

See [`scripts/COMMANDS.md`](scripts/COMMANDS.md) for the launcher, setup scripts, reset scripts, and MCP utility command references.
