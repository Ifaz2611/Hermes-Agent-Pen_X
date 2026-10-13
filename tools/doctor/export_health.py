"""export_health.py

Produce a JSON health report suitable for the Electron dashboard.
Writes data to data/health.json by default.

Collects:
- timestamp
- disk usage for data/ and repo root
- actionable health_checks: missing runtimes, setup state, vault state,
  log excerpts with clear error messages and fix hints
- vault status via src/security/crypto.DataVault
- recent gateway/launch/setup log excerpts
- environment info (python version, platform)
- placeholder for API cost data (looks for data/api_costs.json)
"""
import argparse
import json
import os
import platform
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / 'src'))

try:
    from security.crypto import DataVault
except Exception:
    DataVault = None


def human_size(n):
    if n is None:
        return None
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def dir_size(path: Path):
    total = 0
    try:
        for p in path.rglob('*'):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


def detect_runtime_dir(base_cache: Path):
    """Pick the most relevant runtime dir for this host."""
    runtimes_root = base_cache / 'runtimes'
    candidates = []
    if runtimes_root.is_dir():
        candidates = sorted([p for p in runtimes_root.iterdir() if p.is_dir()])
    # Prefer a dir matching current platform.
    sysname = platform.system().lower()
    arch = platform.machine().lower()
    preferred = None
    if 'windows' in sysname or os.name == 'nt':
        preferred = [p for p in candidates if 'windows' in p.name.lower()]
    elif 'darwin' in sysname:
        preferred = [p for p in candidates if 'macos' in p.name.lower()]
    else:
        preferred = [p for p in candidates if 'linux' in p.name.lower()]
    if preferred:
        return preferred[0]
    if candidates:
        return candidates[0]
    # Default location for this host when nothing exists yet.
    if os.name == 'nt':
        return runtimes_root / 'windows-x64'
    if 'darwin' in sysname:
        arm = 'arm64' in arch or 'aarch64' in arch
        return runtimes_root / ('macos-arm64' if arm else 'macos-x64')
    arm = 'arm64' in arch or 'aarch64' in arch
    return runtimes_root / ('linux-arm64' if arm else 'linux-x64')


def tail_lines(path: Path, max_lines=50, max_bytes=20 * 1024):
    """Read last lines of a text file safely. Returns (lines, truncated)."""
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            to_read = min(size, max_bytes)
            f.seek(-to_read, os.SEEK_END if to_read else 0)
            data = f.read().decode(errors='replace')
            lines = data.splitlines()
            truncated = len(lines) > max_lines or size > max_bytes
            return lines[-max_lines:], truncated
    except Exception as exc:
        return None, False


def error_excerpts(lines, max_items=10):
    """Filter lines that look like errors/warnings."""
    if not lines:
        return []
    pattern = re.compile(r'(error|fail|exception|traceback|warn|denied|missing|not found|cancel)', re.I)
    return [ln[:500] for ln in lines if pattern.search(ln)][:max_items]


def collect_runtimes(runtime_dir: Path):
    """Check for expected runtime components."""
    components = {
        'python': ['python/bin/python3', 'python/python.exe', 'python/bin/python'],
        'node': ['node/bin/node', 'node/node.exe'],
        'uv': ['uv/uv', 'uv/uv.exe'],
        'venv': ['venv/bin/python', 'venv/Scripts/python.exe'],
    }
    present = {}
    missing = []
    for name, rels in components.items():
        found = any((runtime_dir / r).exists() for r in rels)
        present[name] = found
        if not found:
            missing.append(name)
    manifest_path = runtime_dir / 'manifest.json'
    manifest = None
    manifest_error = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception as exc:
            manifest_error = str(exc)
    else:
        manifest_error = 'manifest.json not found — setup may not have completed.'
    ready = (runtime_dir / 'ready.flag').exists()
    progress_path = runtime_dir / 'setup-progress.json'
    progress = None
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding='utf-8'))
        except Exception:
            progress = None
    return {
        'runtime_dir': str(runtime_dir),
        'ready': ready,
        'present': present,
        'missing': missing,
        'manifest': manifest,
        'manifest_error': manifest_error,
        'progress': progress,
    }


def collect_setup_state(data_dir: Path, runtimes: dict):
    """Check .env / config.yaml / ready flag."""
    env_path = data_dir / '.env'
    config_path = data_dir / 'config.yaml'
    configured = False
    provider = None
    model = None
    env_error = None
    config_error = None
    if env_path.exists():
        try:
            text = env_path.read_text(encoding='utf-8', errors='replace')
            configured = bool(re.search(r'^[A-Z][A-Za-z0-9_]*=', text, re.M))
            if not configured:
                env_error = '.env exists but contains no KEY=VALUE entries.'
        except Exception as exc:
            env_error = f'Cannot read .env: {exc}'
    else:
        env_error = '.env not found — run setup to configure a provider.'
    if config_path.exists():
        try:
            text = config_path.read_text(encoding='utf-8', errors='replace')
            m = re.search(r'provider\s*:\s*[\'"\s]*([^\'"\r\n]+)', text)
            d = re.search(r'default\s*:\s*[\'"\s]*([^\'"\r\n]+)', text)
            if m:
                provider = m.group(1).strip()
            if d:
                model = d.group(1).strip()
        except Exception as exc:
            config_error = f'Cannot read config.yaml: {exc}'
    else:
        config_error = 'config.yaml not found — run setup to configure a model.'
    return {
        'configured': configured,
        'provider': provider,
        'model': model,
        'env_exists': env_path.exists(),
        'config_exists': config_path.exists(),
        'env_error': env_error if not configured else None,
        'config_error': config_error if config_path and (provider is None and model is None) else (config_error if not config_path.exists() else None),
        'ready_flag': runtimes.get('ready', False),
    }


def collect_logs(data_dir: Path, repo_root: Path, runtime_dir: Path):
    """Collect useful log excerpts with clear messages when absent."""
    candidates = {
        'gateway': data_dir / 'logs' / 'gateway.log',
        'launch': repo_root / '.cache' / 'logs' / 'launch.log',
        'setup_unix': runtime_dir / 'setup.log',
        'setup_windows': runtime_dir / 'install.log',
    }
    logs = {}
    for key, path in candidates.items():
        entry = {'path': str(path), 'exists': path.exists(), 'lines': None,
                 'error_lines': [], 'truncated': False, 'message': None}
        if path.exists():
            try:
                entry['size_bytes'] = path.stat().st_size
                entry['size_human'] = human_size(entry['size_bytes'])
            except Exception:
                entry['size_bytes'] = None
            lines, truncated = tail_lines(path)
            entry['lines'] = lines
            entry['truncated'] = truncated
            entry['error_lines'] = error_excerpts(lines or [])
            if not lines:
                entry['message'] = f'{path.name} is empty.'
        else:
            entry['message'] = f'{path.name} not found at {path}.'
        logs[key] = entry
    # Back-compat gateway summary used by older dashboard builds.
    gw = logs.get('gateway', {})
    logs_dir = data_dir / 'logs'
    summary = {
        'size_bytes': dir_size(logs_dir) if logs_dir.exists() else None,
        'gateway_last_lines': gw.get('lines'),
        'gateway_log': gw,
        'launch_log': logs.get('launch'),
        'setup_log': logs.get('setup_unix') if logs.get('setup_unix', {}).get('exists') else logs.get('setup_windows'),
    }
    if summary['size_bytes'] is not None:
        summary['size_human'] = human_size(summary['size_bytes'])
    return logs, summary


def build_health_checks(runtimes, setup, vault_report, logs):
    """Build an actionable checklist for the dashboard."""
    checks = []

    def add(cid, label, status, message, hint=None):
        checks.append({'id': cid, 'label': label, 'status': status,
                       'message': message, 'hint': hint})

    # Runtimes
    missing = runtimes.get('missing', [])
    if not runtimes.get('ready') and missing:
        add('runtimes', 'Runtimes', 'error',
            f"Missing runtimes: {', '.join(missing)}. Setup has not completed "
            f"(ready.flag absent in {runtimes.get('runtime_dir')}).",
            'Run the first-run setup from the launcher, then refresh this dashboard.')
    elif missing:
        add('runtimes', 'Runtimes', 'warn',
            f"Partial runtime install — missing: {', '.join(missing)}.",
            'Re-run setup or check the setup log for the failed stage.')
    else:
        add('runtimes', 'Runtimes', 'ok', 'All expected runtimes are present.')

    # Setup state
    if not runtimes.get('ready'):
        add('setup', 'Setup state', 'error',
            'Setup is incomplete (ready.flag missing).',
            'Complete or re-run setup; cancellation leaves a recoverable state — just launch again.')
    elif not setup.get('configured'):
        add('setup', 'Setup state', 'warn',
            setup.get('env_error') or 'Not configured.',
            'Run "hermes setup" or use the launcher Setup action.')
    else:
        detail = 'Configured'
        if setup.get('provider'):
            detail += f" (provider: {setup['provider']}"
            if setup.get('model'):
                detail += f", model: {setup['model']}"
            detail += ')'
        add('setup', 'Setup state', 'ok', detail + '.')

    # Vault state
    if isinstance(vault_report, dict) and 'error' in vault_report and len(vault_report) == 1:
        add('vault', 'Vault state', 'error',
            f"Cannot read vault status: {vault_report['error']}",
            'Check that data/ exists and is readable; see logs below.')
    else:
        enc = vault_report.get('encrypted', False)
        pending = vault_report.get('pending_recovery', False)
        if pending:
            add('vault', 'Vault state', 'warn',
                'An interrupted lock/unlock left recoverable backups.',
                'Run "python -m security recover <data-dir>" then retry the vault operation.')
        elif enc:
            add('vault', 'Vault state', 'ok',
                f"Vault is locked ({vault_report.get('encrypted_files', 0)} encrypted file(s)). "
                'Unlock via the launcher before starting Hermes.')
        else:
            add('vault', 'Vault state', 'ok',
                f"Vault is unlocked ({vault_report.get('total_files', 0)} sensitive file(s) tracked).")

    # Logs
    gw = logs.get('gateway', {})
    if gw.get('exists') and gw.get('error_lines'):
        add('logs', 'Logs', 'warn',
            f"Gateway log shows {len(gw['error_lines'])} error/warning line(s). See excerpts below.",
            'Open the full gateway.log for context; most failures name the missing file or bad value.')
    elif gw.get('exists'):
        add('logs', 'Logs', 'ok', 'Gateway log is available with no obvious errors in the tail.')
    else:
        add('logs', 'Logs', 'info',
            gw.get('message') or 'No gateway log yet.',
            'Logs appear after the first gateway run; this is normal on a fresh install.')

    # Setup log hint when setup failed
    setup_log = logs.get('setup_unix') if logs.get('setup_unix', {}).get('exists') else logs.get('setup_windows')
    if setup_log and setup_log.get('exists') and setup_log.get('error_lines'):
        checks.append({'id': 'setup-log', 'label': 'Setup log', 'status': 'warn',
                       'message': f"Setup log shows {len(setup_log['error_lines'])} error/warning line(s).",
                       'hint': 'The last error line usually names the failed download or stage — re-run setup to resume.'})
    return checks


def collect(data_dir: Path):
    report = {'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}

    # Data directory stats
    report['data_dir'] = str(data_dir)
    if data_dir.exists():
        report['data_dir_size_bytes'] = dir_size(data_dir)
        report['data_dir_size_human'] = human_size(report['data_dir_size_bytes'])
    else:
        report['data_dir_size_bytes'] = None
        report['data_dir_size_human'] = None
        report['data_dir_error'] = (
            f'Data directory not found at {data_dir}. '
            'It is created on first launch; check --data-dir if you use a custom location.'
        )

    # Runtimes
    runtime_dir = detect_runtime_dir(repo_root / '.cache')
    runtimes = collect_runtimes(runtime_dir)
    report['runtimes'] = runtimes

    # Setup state
    setup = collect_setup_state(data_dir, runtimes)
    report['setup'] = setup

    # Vault status
    try:
        if DataVault:
            dv = DataVault(data_dir, password='')  # password not needed to read status
            vault_report = dv.get_vault_status()
            # Attach a human-readable message.
            if vault_report.get('pending_recovery'):
                vault_report['message'] = (
                    'Interrupted vault operation detected — recoverable backups are preserved. '
                    'Run: python -m security recover <data-dir>'
                )
            elif vault_report.get('encrypted'):
                vault_report['message'] = (
                    f"Vault locked ({vault_report.get('encrypted_files', 0)} encrypted file(s))."
                )
            else:
                vault_report['message'] = 'Vault unlocked or not yet encrypted.'
            report['vault'] = vault_report
        else:
            report['vault'] = {'error': 'DataVault unavailable — src/security could not be imported.'}
    except Exception as e:
        report['vault'] = {'error': f'Cannot read vault status: {e}'}

    # Logs
    logs_detail, logs_summary = collect_logs(data_dir, repo_root, runtime_dir)
    report['logs_detail'] = logs_detail
    report['logs'] = logs_summary
    # Back-compat: keep size fields at top level of logs.
    if logs_summary.get('size_bytes') is None and 'size_bytes' not in report['logs']:
        report['logs']['size_bytes'] = None

    # API cost placeholder
    api_costs_file = data_dir / 'api_costs.json'
    if api_costs_file.exists():
        try:
            with open(api_costs_file, 'r', encoding='utf-8') as f:
                report['api_costs'] = json.load(f)
        except Exception as e:
            report['api_costs'] = {'error': f'Cannot parse api_costs.json: {e}'}
    else:
        report['api_costs'] = None

    # Profiles summary
    profiles_dir = data_dir / 'profiles'
    try:
        if profiles_dir.is_dir():
            report['profiles'] = sorted([p.name for p in profiles_dir.iterdir() if p.is_dir()])
        else:
            report['profiles'] = []
    except Exception:
        report['profiles'] = []

    # Env
    report['env'] = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'os': os.name,
    }

    # Actionable checklist (primary UI surface)
    try:
        report['health_checks'] = build_health_checks(runtimes, setup, report['vault'], logs_detail)
    except Exception as exc:
        report['health_checks'] = [{'id': 'internal', 'label': 'Health checks', 'status': 'error',
                                    'message': f'Cannot build health checks: {exc}', 'hint': None}]

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(repo_root / 'data' / 'health.json'))
    parser.add_argument('--data-dir', default=str(repo_root / 'data'))
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    report = collect(Path(args.data_dir))

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print('Wrote health report to', out)


if __name__ == '__main__':
    main()
