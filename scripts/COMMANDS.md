# Command Reference

This guide covers the portable launchers and repository utilities. Hermes CLI subcommands are supplied by the downloaded Hermes source and may vary by version; use `hermes --help` for the commands supported by the installed version.

## Start Hermes

| Platform | Command |
| --- | --- |
| Windows | `.\launch.bat` |
| macOS/Linux | `bash launch.sh` |

Direct launcher commands:

| Platform | Command | Effect |
| --- | --- | --- |
| Windows | `.\launch.bat /silent` | Suppress interactive banners where supported |
| Windows | `.\launch.bat /ramdisk` | Copy runtime/source into a temporary local directory for the run |
| Windows | `.\launch.bat /profile <name>` | Use `data/profiles/<name>` as the data directory |
| macOS/Linux | `bash launch.sh --silent` | Reduce interactive launcher output |
| macOS/Linux | `bash launch.sh --profile <name>` | Use `data/profiles/<name>` as the data directory |
| macOS/Linux | `bash launch.sh --setup` | Force runtime setup again |
| Windows | `.\launch.bat hermes <command>` | Forward a command to Hermes without opening the dashboard |
| macOS/Linux | `bash launch.sh hermes <command>` | Forward a command to Hermes without opening the dashboard |

For help and version options on macOS/Linux, use `bash launch.sh --help` or `bash launch.sh --version`. The Windows launcher forwards Hermes arguments; consult its source for launcher-specific options.

## Runtime setup

Setup normally runs on first launch. To run it directly:

**Windows PowerShell**
```powershell
.\scripts\setup-windows.ps1 -Root $PWD.Path
```

**macOS/Linux**
```bash
bash scripts/setup-unix.sh "$PWD"
```

The Windows script accepts options including `-SkipGit`, `-SkipPlaywright`, `-SkipUv`, `-DryRun`, and `-Launch`. The Unix script accepts `--skip-uv`, `--skip-rg`, `--skip-playwright`, and `--dry-run`. Run either script with its help option for the current option list.

## Hermes CLI

The launcher prepares the environment and can forward Hermes commands:

```text
.\launch.bat hermes --help
.\launch.bat hermes doctor
.\launch.bat hermes setup
```

```bash
bash launch.sh hermes --help
bash launch.sh hermes doctor
bash launch.sh hermes setup
```

The forwarded command set depends on the downloaded Hermes version. For example, to use gateway, config, chat, or session commands, verify their availability with `hermes --help` first.

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

The manager is `tools/mcp/mcp_manager.py`. Use:

```bash
python tools/mcp/mcp_manager.py list
python tools/mcp/mcp_manager.py available
python tools/mcp/mcp_manager.py install filesystem
python tools/mcp/mcp_manager.py add <name> --cmd <command> --env KEY=VALUE --args <arg>...
python tools/mcp/mcp_manager.py remove <name>
```

For custom server registration, `--args` consumes the remaining command-line arguments and must be last. Repeat environment entries as needed; do not put secrets in commands that may be retained in shell history.

### S3 sync

Install `boto3` in the Python environment used to run the script, then review the planned upload:

```bash
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --dry-run
python tools/sync/s3_sync.py --bucket <bucket> --prefix <prefix> --encrypt --password <passphrase>
```

Avoid passing secrets on shared systems or in shell histories. See [`../UX_MANAGEMENT.md`](../UX_MANAGEMENT.md) for data-selection and AWS credential notes.

## Reset scripts

Reset scripts can remove runtime files and, in full mode, user data. Inspect their options and back up `data/` before running.

**Windows PowerShell**
```powershell
.\scripts\reset-windows.ps1 -Mode soft
.\scripts\reset-windows.ps1 -Mode full
```

**macOS/Linux**
```bash
bash scripts/reset-unix.sh soft
bash scripts/reset-unix.sh full
```

Use `full` only when you intend to remove the data covered by that script’s scope.
