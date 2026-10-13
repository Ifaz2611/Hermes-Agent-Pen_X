"""export_health.py

Produce a JSON health report suitable for the Electron dashboard.
Writes data to data/health.json by default.

Collects:
- timestamp
- disk usage for data/ and repo root
- vault status via src/security/crypto.DataVault
- recent gateway log size and last lines if available
- environment info (python version)
- placeholder for API cost data (looks for data/api_costs.json)
"""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / 'src'))

try:
    from security.crypto import DataVault
except Exception as e:
    DataVault = None


def human_size(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def dir_size(path: Path):
    total = 0
    for p in path.rglob('*'):
        if p.is_file():
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return total


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

    # Vault status
    try:
        if DataVault:
            dv = DataVault(data_dir, password='')  # password not needed to read status
            report['vault'] = dv.get_vault_status()
        else:
            report['vault'] = {'error': 'DataVault unavailable'}
    except Exception as e:
        report['vault'] = {'error': str(e)}

    # Logs
    logs_dir = data_dir / 'logs'
    report['logs'] = {}
    if logs_dir.exists():
        report['logs']['size_bytes'] = dir_size(logs_dir)
        report['logs']['size_human'] = human_size(report['logs']['size_bytes'])
        # try to grab last 50 lines of gateway.log if present
        gw = logs_dir / 'gateway.log'
        if gw.exists():
            try:
                with open(gw, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    # read last ~20KB
                    to_read = min(size, 20*1024)
                    f.seek(-to_read, os.SEEK_END)
                    data = f.read().decode(errors='replace')
                    lines = data.splitlines()
                    report['logs']['gateway_last_lines'] = lines[-50:]
            except Exception:
                report['logs']['gateway_last_lines'] = None
    else:
        report['logs']['size_bytes'] = None

    # API cost placeholder
    api_costs_file = data_dir / 'api_costs.json'
    if api_costs_file.exists():
        try:
            with open(api_costs_file, 'r') as f:
                report['api_costs'] = json.load(f)
        except Exception as e:
            report['api_costs'] = {'error': str(e)}
    else:
        report['api_costs'] = None

    # Env
    report['env'] = {
        'python_version': sys.version,
    }

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
