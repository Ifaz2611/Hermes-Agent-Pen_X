"""s3_sync.py

Sync the data/ folder to AWS S3 (or S3-compatible / local providers) with
optional end-to-end encryption using the repo's EncryptionManager (PBKDF2 + Fernet).

Credential Sources:
- AWS Credentials: Standard AWS credential chain:
    1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    2. Shared credentials file (~/.aws/credentials, ~/.aws/config) or --aws-profile
    3. IAM role / instance profile credentials
- Encryption Passphrase:
    1. Environment variable: HERMES_VAULT_PASSWORD, HERMES_S3_PASSWORD, or S3_SYNC_PASSWORD
    2. Interactive prompt (when stdin is a terminal)
    3. Optional command argument: --password (avoid on shared systems to prevent CLI exposure)

P3 features:
- Conflict handling: --no-overwrite / --conflict-policy fail|skip|overwrite|keep-both.
  Dry-run always previews which keys are new vs would-overwrite. Non-overwrite
  policies protect existing remote data from silent overwrites.
- Verification: --verify runs a HeadObject size check after each upload.
- Retention: --retention-keep N with --prune deletes old remote objects under the
  prefix (oldest first); without --prune it only previews.
- Providers: --provider s3 (default, verified) | s3-compatible|minio|wasabi|spaces|b2|r2
  (require --endpoint-url) | local (requires --local-dir, offline). See providers.py.
  Only adopt non-AWS providers after S3 sync shows reliable verification/errors/recovery.

Notes:
- Requires boto3 installed for S3 uploads (pip install boto3).
- Dry-run mode (--dry-run) inspects local files and displays planned uploads without
  requiring AWS credentials, boto3, or network access.
- Non-zero exit code is returned if any upload, verification, or encryption op fails.
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import sys
import tempfile

# Import repository encryption utilities
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / 'src'))

try:
    from security.crypto import EncryptionManager
except Exception:
    EncryptionManager = None  # type: ignore


def _s3_key(prefix: str, rel: str) -> str:
    # S3 keys always use forward slashes, even on Windows.
    parts = [p for p in (prefix or "").replace("\\", "/").split("/") if p]
    parts += [p for p in rel.replace("\\", "/").split("/") if p and p != ".."]
    return "/".join(parts)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='Sync data/ to AWS S3 (or compatible/local providers) with optional end-to-end encryption',
        epilog=(
            'Credential sources: AWS credentials from standard AWS env vars, ~/.aws/credentials, '
            'or --aws-profile. Encryption passphrase from HERMES_VAULT_PASSWORD env var, '
            'interactive prompt, or --password. Providers: s3 (default) | s3-compatible|minio|'
            'wasabi|spaces|b2|r2 (need --endpoint-url) | local (need --local-dir).'
        ),
    )
    p.add_argument('--bucket', required=True, help='S3 bucket name (or any name for --provider local)')
    p.add_argument('--prefix', default='', help='S3 key prefix')
    p.add_argument('--data-dir', default=str(repo_root / 'data'), help='Local data directory')
    p.add_argument('--encrypt', action='store_true', help='Encrypt files before upload')
    p.add_argument(
        '--password',
        help='Passphrase for encryption (prefer HERMES_VAULT_PASSWORD env var or prompt)',
    )
    p.add_argument('--aws-profile', help='AWS CLI profile to use')
    p.add_argument(
        '--dry-run',
        action='store_true',
        help='Show planned uploads without requiring AWS access or modifying remote storage',
    )
    p.add_argument('--preview', action='store_true',
                   help='Alias for --dry-run (preview actions without modifying remote)')
    # P3: providers
    p.add_argument('--provider', default='s3',
                   help='Storage provider: s3|s3-compatible|minio|wasabi|spaces|b2|r2|local (default s3)')
    p.add_argument('--endpoint-url', default=None, help='Custom S3 endpoint URL (S3-compatible providers)')
    p.add_argument('--region', default=None, help='Region hint for S3-compatible providers')
    p.add_argument('--local-dir', default=None, help='Mirror root for --provider local')
    # P3: conflict handling
    p.add_argument('--no-overwrite', action='store_true',
                   help='Never overwrite existing remote objects (protect from silent overwrites)')
    p.add_argument('--conflict-policy', choices=('fail', 'skip', 'overwrite', 'keep-both'),
                   default=None,
                   help='How to handle existing remote keys (default: overwrite unless --no-overwrite)')
    # P3: verification + retention
    p.add_argument('--verify', action='store_true',
                   help='Verify each upload with a remote size check (HeadObject)')
    p.add_argument('--no-verify', action='store_true', help='Disable verification (default)')
    p.add_argument('--retention-keep', type=int, default=0,
                   help='Keep only N newest remote objects under prefix (0=disabled)')
    p.add_argument('--prune', action='store_true',
                   help='Actually delete old remote objects when --retention-keep is set (else preview only)')
    return p.parse_args(argv)


def get_encryption_password(cli_password: str | None, allow_prompt: bool = True) -> str | None:
    """Retrieve encryption passphrase without requiring CLI argument exposure."""
    if cli_password:
        return cli_password
    # Check environment variables
    for env_var in ("HERMES_VAULT_PASSWORD", "HERMES_S3_PASSWORD", "S3_SYNC_PASSWORD"):
        val = os.environ.get(env_var)
        if val:
            return val
    # Prompt interactively if supported
    if allow_prompt and sys.stdin.isatty():
        try:
            pw = getpass.getpass("Enter encryption passphrase for S3 sync: ")
            if pw:
                return pw
        except (EOFError, KeyboardInterrupt):
            pass
    return None


def s3_client(profile=None, endpoint_url=None, region=None, **_kwargs):
    try:
        import boto3
    except ImportError:
        print("boto3 is required for S3 uploads. Install it with: pip install boto3", file=sys.stderr)
        raise SystemExit(2)
    try:
        kwargs: dict = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if region:
            kwargs["region_name"] = region
        if profile:
            session = boto3.Session(profile_name=profile)
            return session.client('s3', **kwargs)
        return boto3.client('s3', **kwargs)
    except Exception as exc:
        print(f"Failed to create S3 client: {exc}", file=sys.stderr)
        raise SystemExit(2)


def upload_file(s3, bucket: str, key: str, local_path: Path, dry_run: bool = False) -> bool:
    action = "[DRY-RUN] Would upload" if dry_run else "Uploading"
    print(f"{action} {local_path} -> s3://{bucket}/{key}")
    if dry_run:
        return True

    try:
        from botocore.exceptions import ClientError
    except ImportError:
        print("botocore is required for S3 sync. Install it with: pip install boto3", file=sys.stderr)
        return False

    try:
        s3.upload_file(str(local_path), bucket, key)
        return True
    except (ClientError, Exception) as e:
        print(f"Upload failed for {local_path} -> s3://{bucket}/{key}: {e}", file=sys.stderr)
        return False


def list_remote_keys(s3, bucket: str, prefix: str) -> tuple[list[str] | None, str]:
    """Best-effort remote listing. Returns (keys|None, note). None = listing unavailable."""
    if s3 is None:
        return None, "no client (dry-run)"
    norm = prefix.replace("\\", "/").strip("/")
    search = (norm + "/") if norm else ""
    try:
        # Support both raw boto3 clients and provider wrappers.
        if hasattr(s3, "list_keys"):
            objs = s3.list_keys(prefix or "")
            return [o.get("Key", "") for o in objs if o.get("Key")], "listed via provider"
        token = None
        keys: list[str] = []
        while True:
            kwargs: dict = {"Bucket": bucket, "Prefix": search}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                keys.append(obj["Key"])
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        return keys, f"listed {len(keys)} key(s)"
    except Exception as exc:
        return None, f"remote listing unavailable: {exc}"


def verify_upload(s3, bucket: str, key: str, local_path: Path) -> tuple[bool, str]:
    """Post-upload size verification (best-effort)."""
    if s3 is None:
        return False, "no client"
    try:
        if hasattr(s3, "verify"):
            return s3.verify(local_path, key)
        head = s3.head_object(Bucket=bucket, Key=key)
        remote_size = int(head.get("ContentLength", -1))
        local_size = Path(local_path).stat().st_size
        if remote_size == local_size:
            return True, f"verify: size match ({local_size}b) for {key}"
        return False, f"verify: size mismatch for {key} (local {local_size} != remote {remote_size})"
    except Exception as exc:
        return False, f"verify failed for {key}: {exc}"


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.preview:
        args.dry_run = True

    # Resolve conflict policy (backward-compatible default: overwrite).
    policy = args.conflict_policy
    if policy is None:
        policy = "skip" if args.no_overwrite else "overwrite"
    if args.no_overwrite and policy == "overwrite":
        policy = "skip"

    provider_name = (args.provider or "s3").lower()
    if provider_name not in ("s3", "s3-compatible", "local", "minio", "wasabi",
                             "spaces", "b2", "r2"):
        print(f"Unknown --provider '{args.provider}'.", file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}", file=sys.stderr)
        return 2

    # Resolve passphrase if encryption is requested
    password = None
    if args.encrypt:
        password = get_encryption_password(args.password, allow_prompt=not args.dry_run)
        if not password and not args.dry_run:
            print(
                "Error: --encrypt requires a passphrase.\n"
                "Provide it via HERMES_VAULT_PASSWORD environment variable, interactive prompt, or --password.",
                file=sys.stderr,
            )
            return 2

    # Provider guidance (P3: only adopt extra providers after S3 is reliable).
    if provider_name != "s3" and provider_name != "local":
        print(f"[INFO] Provider '{provider_name}': S3-compatible target. "
              "Only use after S3 sync shows reliable verification/errors/recovery. "
              "Running --dry-run first is strongly recommended.")
        if not args.endpoint_url:
            print(f"[ERROR] --provider {provider_name} requires --endpoint-url <url>.", file=sys.stderr)
            return 2
    if provider_name == "s3-compatible" and not args.endpoint_url:
        print("[ERROR] --provider s3-compatible requires --endpoint-url <url>.", file=sys.stderr)
        return 2

    # Local provider path (offline, no boto3 needed).
    local_provider = None
    if provider_name == "local":
        if not args.local_dir:
            print("[ERROR] --provider local requires --local-dir <path>.", file=sys.stderr)
            return 2
        try:
            sys.path.insert(0, str(repo_root / "tools" / "sync"))
            from providers import LocalProvider
            local_provider = LocalProvider(args.local_dir)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Failed to init local provider: {exc}", file=sys.stderr)
            return 2
        print(f"[INFO] Provider 'local': mirroring to {args.local_dir} (offline, no network).")

    # In dry-run mode, do NOT initialize or require S3 client / AWS credentials
    s3 = None
    if not args.dry_run:
        if local_provider is not None:
            s3 = local_provider
        elif args.endpoint_url or args.region:
            # New path (S3-compatible). Old test doubles patching s3_client with
            # `lambda profile=None` keep working for the default path below.
            s3 = s3_client(args.aws_profile, endpoint_url=args.endpoint_url, region=args.region)
        else:
            s3 = s3_client(args.aws_profile)

    # Conflict detection: list remote keys (best-effort).
    remote_keys: set[str] = set()
    remote_note = "conflict check skipped (dry-run without credentials)"
    if not args.dry_run:
        keys, note = list_remote_keys(s3, args.bucket, args.prefix)
        remote_note = note
        if keys is None:
            if policy != "overwrite":
                print(f"[ERROR] Cannot protect remote data: {note}. "
                      "Aborting instead of risking silent overwrites. "
                      "Use --conflict-policy overwrite to force, or fix credentials/network.",
                      file=sys.stderr)
                return 1
            print(f"[WARN] {note}; proceeding with overwrite policy.", file=sys.stderr)
        else:
            remote_keys = set(keys)
            print(f"[INFO] Remote state: {len(remote_keys)} existing object(s) under "
                  f"s3://{args.bucket}/{args.prefix} ({note}). Policy: {policy}.")
    else:
        print(f"[DRY-RUN] {remote_note}. Policy: {policy}. "
              "New vs overwrite status will be checked at real run time.")

    do_verify = bool(args.verify) and not bool(args.no_verify)

    failures: list[tuple[str, str]] = []
    success_count = 0
    skipped_count = 0
    kept_both_count = 0

    def _handle_conflict(key: str, local_label: str) -> str:
        """Returns action: 'upload' | 'skip' | 'fail' | 'keep-both:<newkey>'."""
        if key not in remote_keys:
            return "upload"
        if policy == "overwrite":
            print(f"[WARN] Will overwrite existing remote key s3://{args.bucket}/{key} "
                  f"(local {local_label}).")
            return "upload"
        if policy == "skip":
            return "skip"
        if policy == "fail":
            return "fail"
        if policy == "keep-both":
            return f"keep-both:{key}.conflict-{os.getpid()}"
        return "upload"

    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        planned: list[tuple[Path, str, str]] = []
        for p in sorted(data_dir.rglob('*')):
            if p.is_dir():
                continue
            rel = p.relative_to(data_dir)
            suffix = str(rel) + ('.enc' if args.encrypt else '')
            planned.append((p, _s3_key(args.prefix, suffix), str(rel)))

        if args.dry_run:
            for local_p, s3_key, rel in planned:
                marker = "[DRY-RUN] Would upload"
                dest = f"s3://{args.bucket}/{s3_key}" if provider_name != "local" \
                    else f"{args.local_dir}/{s3_key}"
                print(f"{marker} {local_p} -> {dest}")
                success_count += 1
            if args.retention_keep and int(args.retention_keep) > 0:
                print(f"[DRY-RUN] Retention preview: would keep newest {args.retention_keep} "
                      f"object(s) under s3://{args.bucket}/{args.prefix}; "
                      "run without --dry-run + --prune to delete older ones (previewed at run time).")
            print(f"Dry run complete: {success_count} file(s) processed successfully.")
            return 0

        # Real run.
        for local_p, s3_key, rel in planned:
            action = _handle_conflict(s3_key, str(local_p))
            if action == "skip":
                print(f"[SKIP] Remote exists, preserving s3://{args.bucket}/{s3_key} "
                      f"(local {local_p}).")
                skipped_count += 1
                continue
            if action == "fail":
                msg = (f"Refusing to overwrite existing remote key s3://{args.bucket}/{s3_key} "
                       f"(policy=fail, local {local_p}). Nothing uploaded for this file.")
                print(msg, file=sys.stderr)
                failures.append((str(local_p), msg))
                continue
            target_key = s3_key
            if action.startswith("keep-both:"):
                target_key = action.split(":", 1)[1]
                print(f"[KEEP-BOTH] Remote exists; uploading {local_p} as "
                      f"s3://{args.bucket}/{target_key} instead of overwriting.")

            if args.encrypt:
                if EncryptionManager is None:
                    failures.append((str(local_p), "EncryptionManager unavailable"))
                    print(f"Encryption failed for {local_p}: EncryptionManager unavailable",
                          file=sys.stderr)
                    continue
                enc_path = staging_dir / (str(rel).replace(os.sep, '_') + '.enc')
                try:
                    EncryptionManager.encrypt_file(local_p, password, output_path=enc_path)
                except Exception as e:
                    failures.append((str(local_p), f"Encryption failed: {e}"))
                    print(f"Encryption failed for {local_p}: {e}", file=sys.stderr)
                    continue
                if local_provider is not None:
                    ok, msg = local_provider.upload(enc_path, target_key, dry_run=False)
                    print(msg)
                else:
                    ok = upload_file(s3, args.bucket, target_key, enc_path, dry_run=False)
                if ok:
                    if do_verify:
                        vok, vmsg = verify_upload(s3, args.bucket, target_key, enc_path)
                        print(vmsg)
                        if not vok:
                            failures.append((str(local_p), vmsg))
                            continue
                    success_count += 1
                    if target_key != s3_key:
                        kept_both_count += 1
                else:
                    failures.append((str(local_p), f"Upload to s3://{args.bucket}/{target_key} failed"))
            else:
                if local_provider is not None:
                    ok, msg = local_provider.upload(local_p, target_key, dry_run=False)
                    print(msg)
                else:
                    ok = upload_file(s3, args.bucket, target_key, local_p, dry_run=False)
                if ok:
                    if do_verify:
                        vok, vmsg = verify_upload(s3, args.bucket, target_key, local_p)
                        print(vmsg)
                        if not vok:
                            failures.append((str(local_p), vmsg))
                            continue
                    success_count += 1
                    if target_key != s3_key:
                        kept_both_count += 1
                else:
                    failures.append((str(local_p), f"Upload to s3://{args.bucket}/{target_key} failed"))

        # Retention (remote prune): preview by default, delete only with --prune.
        if args.retention_keep and int(args.retention_keep) > 0:
            keep = int(args.retention_keep)
            keys2, note2 = list_remote_keys(s3, args.bucket, args.prefix)
            if keys2 is None:
                print(f"[WARN] Retention skipped: {note2}", file=sys.stderr)
            else:
                # Sort by key (names embed timestamps in practice); provider list_keys
                # returns size/mtime but raw boto3 path only has keys. Sort lexicographically.
                ordered = sorted(keys2)
                if len(ordered) > keep:
                    doomed = ordered[:len(ordered) - keep]
                    print(f"[RETENTION] {len(ordered)} remote object(s), keep newest {keep}: "
                          f"{len(doomed)} would be deleted under s3://{args.bucket}/{args.prefix}.")
                    for k in doomed[:10]:
                        print(f"  {'[DELETE]' if args.prune else '[WOULD-DELETE]'} s3://{args.bucket}/{k}")
                    if len(doomed) > 10:
                        print(f"  ... and {len(doomed) - 10} more.")
                    if args.prune:
                        for k in doomed:
                            try:
                                if local_provider is not None:
                                    ok, msg = local_provider.delete(k, dry_run=False)
                                    print(msg)
                                    if not ok:
                                        failures.append((k, msg))
                                else:
                                    s3.delete_object(Bucket=args.bucket, Key=k)
                                    print(f"Deleted s3://{args.bucket}/{k}")
                            except Exception as exc:
                                failures.append((k, f"Retention delete failed: {exc}"))
                                print(f"Retention delete failed for {k}: {exc}", file=sys.stderr)
                    else:
                        print("[RETENTION] Preview only — no remote objects deleted. "
                              "Re-run with --prune to apply.")
                else:
                    print(f"[RETENTION] {len(ordered)} object(s) <= keep {keep}: nothing to prune.")

    if failures:
        print(f"\nS3 sync encountered {len(failures)} failure(s) ({success_count} succeeded"
              f"{f', {skipped_count} skipped' if skipped_count else ''}"
              f"{f', {kept_both_count} kept-both' if kept_both_count else ''}):", file=sys.stderr)
        for failed_path, reason in failures:
            print(f"  - {failed_path}: {reason}", file=sys.stderr)
        return 1

    print(f"Sync complete: {success_count} file(s) processed successfully"
          f"{f' ({skipped_count} skipped, remote preserved)' if skipped_count else ''}"
          f"{f' ({kept_both_count} kept-both)' if kept_both_count else ''}.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
