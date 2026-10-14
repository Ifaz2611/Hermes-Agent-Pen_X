"""schedule_manager.py

Scheduled backup/sync support for Hermes Agent Pendrive_X (P3 — optional).

Design principles (per TODO):
- Schedules are strictly OPT-IN: no schedule file => disabled. `enable` creates it.
- Explain WHAT data is uploaded: every status/preview lists the source directory,
  file count, total bytes, encrypted-file count, and the destination.
- Clear pause/disable control: `pause`, `resume`, `disable` (+ `status`).

The scheduler itself is a lightweight interval tracker (no background daemon):
- `enable --interval-hours N --mode backup|s3 ...` writes .cache/sync_schedule.json.
- `check [--run-if-due]` is meant to be called from cron / Task Scheduler /
  systemd timers or manually; it runs the job only when due, enabled, and not paused.
- `run-now` forces an immediate run (with optional --dry-run preview).

No passwords are stored in the schedule file. Encryption passphrases must come
from HERMES_VAULT_PASSWORD env var or an interactive prompt at run time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_FILENAME = "sync_schedule.json"


def find_repo_root(custom_root: Optional[Path] = None) -> Path:
    if custom_root:
        return custom_root.resolve()
    return Path(__file__).resolve().parents[2]


def schedule_path(root: Path) -> Path:
    return root / ".cache" / DEFAULT_FILENAME


def load_schedule(root: Path) -> Optional[Dict[str, Any]]:
    p = schedule_path(root)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_schedule(root: Path, data: Dict[str, Any]) -> Path:
    p = schedule_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def describe_source(data_dir: Path) -> Dict[str, Any]:
    """Summarise WHAT would be uploaded (read-only scan)."""
    data_dir = data_dir.resolve() if data_dir.is_absolute() else data_dir
    files = []
    total_bytes = 0
    encrypted = 0
    if data_dir.is_dir():
        for p in sorted(data_dir.rglob("*")):
            if p.is_file():
                try:
                    sz = p.stat().st_size
                except OSError:
                    continue
                total_bytes += sz
                files.append(str(p.relative_to(data_dir)).replace("\\", "/"))
                try:
                    head = p.read_bytes()[:128]
                    if b'"vault_version"' in head or b'"ciphertext"' in head:
                        encrypted += 1
                except Exception:
                    pass
    return {
        "data_dir": str(data_dir),
        "exists": data_dir.is_dir(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "encrypted_files": encrypted,
        "sample": files[:8],
    }


def explain_schedule(sched: Dict[str, Any], root: Path) -> str:
    src = describe_source(Path(sched.get("data_dir", str(root / "data"))))
    lines = []
    lines.append("Hermes scheduled backup/sync — opt-in schedule")
    lines.append(f"  Enabled : {sched.get('enabled', False)}")
    lines.append(f"  Paused  : {sched.get('paused', False)}")
    lines.append(f"  Mode    : {sched.get('mode', 'backup')}")
    lines.append(f"  Interval: every {sched.get('interval_hours', 24)} hour(s)")
    lines.append(f"  Last run: {sched.get('last_run') or 'never'}")
    lines.append(f"  Next run: {sched.get('next_run') or 'as soon as enabled'}")
    lines.append("")
    lines.append("What data is uploaded:")
    lines.append(f"  Source directory : {src['data_dir']} (exists={src['exists']})")
    lines.append(f"  Files            : {src['file_count']} file(s), {src['total_bytes']} bytes")
    lines.append(f"  Vault-encrypted  : {src['encrypted_files']} file(s) (backed up as ciphertext; "
                 "passphrase never uploaded)")
    if src["sample"]:
        lines.append(f"  Sample           : {', '.join(src['sample'])}")
    lines.append("")
    if sched.get("mode") == "s3":
        lines.append(f"Destination (S3): s3://{sched.get('bucket', '?')}/"
                     f"{sched.get('prefix', '')} (provider={sched.get('provider', 's3')})")
        if sched.get("endpoint_url"):
            lines.append(f"  Endpoint: {sched.get('endpoint_url')}")
        lines.append(f"  Encrypt before upload: {bool(sched.get('encrypt', False))} "
                     "(passphrase from HERMES_VAULT_PASSWORD env var, never stored)")
    else:
        lines.append(f"Destination (backup): {sched.get('destination', '.cache/backups/')} "
                     "(.zip archives with SHA-256 manifest)")
        lines.append(f"  Retention: keep last {sched.get('retention_keep', 0) or 'unlimited'} backup(s)")
    lines.append("")
    lines.append("Controls: `schedule pause` (temporarily stop), `schedule resume`, "
                 "`schedule disable` (opt out), `schedule run-now --dry-run` (preview).")
    return "\n".join(lines)


def is_due(sched: Dict[str, Any], now: Optional[datetime] = None) -> Tuple[bool, str]:
    if not sched.get("enabled", False):
        return False, "schedule is disabled (opt-in required; use `schedule enable`)"
    if sched.get("paused", False):
        return False, "schedule is paused (use `schedule resume` to continue)"
    now = now or datetime.now(timezone.utc)
    nxt = sched.get("next_run")
    if not nxt:
        return True, "never ran before — due now"
    try:
        nxt_dt = datetime.fromisoformat(nxt.replace("Z", "+00:00"))
    except Exception:
        return True, "next_run unreadable — due now"
    if now >= nxt_dt:
        return True, f"due (now={now.isoformat()}, next_run={nxt})"
    return False, f"not due until {nxt}"


def mark_ran(sched: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    interval = float(sched.get("interval_hours", 24))
    sched["last_run"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sched["next_run"] = (now + timedelta(hours=interval)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return sched


def cmd_status(root: Path) -> int:
    sched = load_schedule(root)
    if not sched:
        print("Scheduled backup/sync: DISABLED (opt-in).")
        print("No schedule file found. Nothing is uploaded automatically.")
        print("")
        print("To opt in, e.g.:")
        print("  python tools/sync/schedule_manager.py enable --interval-hours 24 --mode backup")
        print("  python tools/sync/schedule_manager.py enable --interval-hours 12 --mode s3 "
              "--bucket my-bucket --prefix hermes/ --encrypt")
        print("")
        print("What WOULD be uploaded (current data/ scan):")
        src = describe_source(root / "data")
        print(f"  {src['file_count']} file(s), {src['total_bytes']} bytes, "
              f"{src['encrypted_files']} encrypted, from {src['data_dir']}")
        return 0
    print(explain_schedule(sched, root))
    due, reason = is_due(sched)
    print(f"Due check: {'DUE' if due else 'NOT DUE'} — {reason}")
    return 0


def cmd_enable(root: Path, args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir) if args.data_dir else (root / "data")
    sched: Dict[str, Any] = load_schedule(root) or {}
    sched.update({
        "enabled": True,
        "paused": False,
        "interval_hours": args.interval_hours,
        "mode": args.mode,
        "data_dir": str(data_dir.resolve() if data_dir.is_absolute() else (root / data_dir).resolve()
                        if not data_dir.is_absolute() and args.data_dir else data_dir),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if args.mode == "s3":
        if not args.bucket:
            print("[ERROR] --mode s3 requires --bucket <name>", file=sys.stderr)
            return 2
        sched.update({
            "bucket": args.bucket,
            "prefix": args.prefix or "",
            "provider": args.provider or "s3",
            "endpoint_url": args.endpoint_url or "",
            "region": args.region or "",
            "encrypt": bool(args.encrypt),
            "no_overwrite": bool(args.no_overwrite),
        })
        if args.provider and args.provider != "s3" and not args.endpoint_url and args.provider != "local":
            print(f"[WARN] Provider '{args.provider}' without --endpoint-url; "
                  "S3-compatible targets need an endpoint. See providers.py.", file=sys.stderr)
    else:
        sched.update({
            "destination": args.destination or "",
            "retention_keep": int(args.retention_keep or 0),
        })
    # (Re)compute next run from now.
    now = datetime.now(timezone.utc)
    if not sched.get("last_run"):
        sched["next_run"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    p = save_schedule(root, sched)
    print(f"[OK] Schedule enabled (opt-in). Saved to {p}")
    print("")
    print(explain_schedule(sched, root))
    print("")
    print("Preview first with: python tools/sync/schedule_manager.py run-now --dry-run")
    return 0


def cmd_disable(root: Path) -> int:
    sched = load_schedule(root)
    if not sched:
        print("No schedule to disable (already opt-out).")
        return 0
    sched["enabled"] = False
    save_schedule(root, sched)
    print("[OK] Schedule disabled. No automatic uploads will occur.")
    print("Re-enable with `schedule enable ...`. Config file preserved.")
    return 0


def cmd_pause(root: Path) -> int:
    sched = load_schedule(root)
    if not sched or not sched.get("enabled"):
        print("[ERROR] No enabled schedule to pause. Use `schedule enable` first.",
              file=sys.stderr)
        return 1
    sched["paused"] = True
    save_schedule(root, sched)
    print("[OK] Schedule paused. Automatic runs are suspended until `schedule resume`.")
    return 0


def cmd_resume(root: Path) -> int:
    sched = load_schedule(root)
    if not sched or not sched.get("enabled"):
        print("[ERROR] No enabled schedule to resume.", file=sys.stderr)
        return 1
    sched["paused"] = False
    save_schedule(root, sched)
    print("[OK] Schedule resumed.")
    return 0


def _run_backup_job(sched: Dict[str, Any], root: Path, dry_run: bool) -> int:
    from tools.backup.backup_manager import create_backup, prune_backups

    src = Path(sched.get("data_dir") or str(root / "data"))
    dest_raw = sched.get("destination") or ""
    dest = Path(dest_raw) if dest_raw else None
    print("[SCHEDULE] Mode: local backup")
    print(f"[SCHEDULE] Source: {src}")
    info = describe_source(src)
    print(f"[SCHEDULE] Uploading {info['file_count']} file(s) ({info['total_bytes']} bytes, "
          f"{info['encrypted_files']} encrypted) to {dest or '.cache/backups/'}")
    if dry_run:
        print("[DRY-RUN] Would create backup now (no files written).")
        keep = int(sched.get("retention_keep") or 0)
        if keep > 0:
            print(f"[DRY-RUN] Retention: would keep last {keep} backup(s), preview with "
                  "`backup prune --dry-run`.")
        return 0
    rc, out_path, manifest = create_backup(source_dir=src, dest_path=dest, repo_root=root)
    if rc != 0:
        return rc
    keep = int(sched.get("retention_keep") or 0)
    if keep > 0:
        backup_dir = out_path.parent if str(out_path).endswith(".zip") else out_path
        prc, msg, _ = prune_backups(backup_dir, keep_last_n=keep, dry_run=False)
        print(f"[SCHEDULE] Retention: {msg} (rc={prc})")
    return 0


def _run_s3_job(sched: Dict[str, Any], root: Path, dry_run: bool) -> int:
    # Lazy import so schedule manager works without boto3 for dry runs.
    sys.path.insert(0, str(root / "tools" / "sync"))
    sys.path.insert(0, str(root / "src"))
    from s3_sync import main as s3_main

    argv = ["--bucket", sched.get("bucket", ""),
            "--prefix", sched.get("prefix", ""),
            "--data-dir", sched.get("data_dir") or str(root / "data"),
            "--provider", sched.get("provider") or "s3"]
    if sched.get("endpoint_url"):
        argv += ["--endpoint-url", sched["endpoint_url"]]
    if sched.get("region"):
        argv += ["--region", sched["region"]]
    if sched.get("encrypt"):
        argv += ["--encrypt"]
    if sched.get("no_overwrite"):
        argv += ["--no-overwrite"]
    if dry_run:
        argv += ["--dry-run"]
    print("[SCHEDULE] Mode: S3 sync")
    print(f"[SCHEDULE] Destination: s3://{sched.get('bucket')}/{sched.get('prefix')} "
          f"(provider={sched.get('provider')})")
    return s3_main(argv)


def cmd_run(root: Path, dry_run: bool, force: bool = False) -> int:
    sched = load_schedule(root)
    if not sched:
        print("[ERROR] No schedule configured. Use `schedule enable` to opt in first.",
              file=sys.stderr)
        return 1
    if not force:
        due, reason = is_due(sched)
        print(f"[SCHEDULE] Due check: {reason}")
        if not due and not dry_run:
            print("[SCHEDULE] Not due — use `run-now` to force, or wait until next_run.")
            return 0
    else:
        print("[SCHEDULE] Forced run (ignoring due time). Paused/disabled still respected.")
        if not sched.get("enabled", False):
            print("[ERROR] Schedule is disabled. Re-enable first.", file=sys.stderr)
            return 1
        if sched.get("paused", False):
            print("[ERROR] Schedule is paused. Resume first (`schedule resume`).",
                  file=sys.stderr)
            return 1
    print(explain_schedule(sched, root))
    if sched.get("mode") == "s3":
        rc = _run_s3_job(sched, root, dry_run=dry_run)
    else:
        rc = _run_backup_job(sched, root, dry_run=dry_run)
    if rc == 0 and not dry_run:
        mark_ran(sched)
        save_schedule(root, sched)
        print(f"[SCHEDULE] Recorded run. Next run: {sched.get('next_run')}")
    elif dry_run:
        print("[DRY-RUN] Preview only — last_run/next_run unchanged.")
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Opt-in scheduled backup/sync (pause/disable supported; passwords never stored).")
    p.add_argument("--root", type=Path, default=None, help="Repository root path")
    sub = p.add_subparsers(dest="action", help="Schedule action")

    sub.add_parser("status", help="Show schedule, what is uploaded, and due state")

    pe = sub.add_parser("enable", help="Opt in to scheduled backups/sync")
    pe.add_argument("--interval-hours", type=float, default=24.0,
                    help="Run interval in hours (default 24)")
    pe.add_argument("--mode", choices=("backup", "s3"), default="backup")
    pe.add_argument("--data-dir", default=None, help="Source data directory")
    pe.add_argument("--destination", default=None, help="Backup destination (mode=backup)")
    pe.add_argument("--retention-keep", type=int, default=0,
                    help="Keep last N backups (mode=backup, 0=unlimited)")
    pe.add_argument("--bucket", default=None, help="S3 bucket (mode=s3)")
    pe.add_argument("--prefix", default="", help="S3 key prefix (mode=s3)")
    pe.add_argument("--provider", default="s3", help="Storage provider (mode=s3)")
    pe.add_argument("--endpoint-url", default=None, help="Custom S3 endpoint (S3-compatible)")
    pe.add_argument("--region", default=None, help="Region / location hint")
    pe.add_argument("--encrypt", action="store_true", help="Encrypt before S3 upload")
    pe.add_argument("--no-overwrite", action="store_true",
                    help="Never overwrite existing remote objects")

    sub.add_parser("disable", help="Opt out (disable automatic runs, keep config)")
    sub.add_parser("pause", help="Temporarily suspend automatic runs")
    sub.add_parser("resume", help="Resume a paused schedule")

    pr = sub.add_parser("run-now", help="Force an immediate run (preview with --dry-run)")
    pr.add_argument("--dry-run", action="store_true", help="Preview without uploading/writing")

    pc = sub.add_parser("check", help="Run only if due (for cron / Task Scheduler)")
    pc.add_argument("--run-if-due", action="store_true",
                    help="Actually run when due (default is check-only)")
    pc.add_argument("--dry-run", action="store_true", help="Preview only")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = find_repo_root(args.root)
    if args.action == "status" or args.action is None:
        return cmd_status(root)
    if args.action == "enable":
        if args.interval_hours <= 0:
            print("[ERROR] --interval-hours must be > 0", file=sys.stderr)
            return 2
        return cmd_enable(root, args)
    if args.action == "disable":
        return cmd_disable(root)
    if args.action == "pause":
        return cmd_pause(root)
    if args.action == "resume":
        return cmd_resume(root)
    if args.action == "run-now":
        return cmd_run(root, dry_run=bool(args.dry_run), force=True)
    if args.action == "check":
        sched = load_schedule(root)
        if not sched:
            print("No schedule configured (disabled).")
            return 0
        due, reason = is_due(sched)
        print(f"Due check: {'DUE' if due else 'NOT DUE'} — {reason}")
        if due and args.run_if_due:
            return cmd_run(root, dry_run=bool(args.dry_run), force=False)
        if due and not args.run_if_due:
            print("Use `check --run-if-due` to execute, or `run-now --dry-run` to preview.")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
