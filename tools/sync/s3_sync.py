"""s3_sync.py

Sync the data/ folder to AWS S3 with optional end-to-end encryption using the repo's
EncryptionManager (PBKDF2 + Fernet).

Credential Sources:
- AWS Credentials: Standard AWS credential chain:
    1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    2. Shared credentials file (~/.aws/credentials, ~/.aws/config) or --aws-profile
    3. IAM role / instance profile credentials
- Encryption Passphrase:
    1. Environment variable: HERMES_VAULT_PASSWORD, HERMES_S3_PASSWORD, or S3_SYNC_PASSWORD
    2. Interactive prompt (when stdin is a terminal)
    3. Optional command argument: --password (avoid on shared systems to prevent CLI exposure)

Notes:
- Requires boto3 installed for uploads (pip install boto3).
- Dry-run mode (--dry-run) inspects local files and displays planned uploads without
  requiring AWS credentials, boto3, or network access.
- Non-zero exit code is returned if any upload or encryption operation fails.
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
except Exception as e:
    EncryptionManager = None  # type: ignore


def _s3_key(prefix: str, rel: str) -> str:
    # S3 keys always use forward slashes, even on Windows.
    parts = [p for p in (prefix or "").replace("\\", "/").split("/") if p]
    parts += [p for p in rel.replace("\\", "/").split("/") if p and p != ".."]
    return "/".join(parts)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='Sync data/ to AWS S3 with optional end-to-end encryption',
        epilog=(
            'Credential sources: AWS credentials from standard AWS env vars, ~/.aws/credentials, '
            'or --aws-profile. Encryption passphrase from HERMES_VAULT_PASSWORD env var, '
            'interactive prompt, or --password.'
        ),
    )
    p.add_argument('--bucket', required=True, help='S3 bucket name')
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


def s3_client(profile=None):
    try:
        import boto3
    except ImportError:
        print("boto3 is required for S3 uploads. Install it with: pip install boto3", file=sys.stderr)
        raise SystemExit(2)
    try:
        if profile:
            session = boto3.Session(profile_name=profile)
            return session.client('s3')
        return boto3.client('s3')
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


def main(argv=None) -> int:
    args = parse_args(argv)

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

    # In dry-run mode, do NOT initialize or require S3 client / AWS credentials
    s3 = None if args.dry_run else s3_client(args.aws_profile)

    failures: list[tuple[str, str]] = []
    success_count = 0

    with tempfile.TemporaryDirectory() as staging:
        staging_dir = Path(staging)
        for p in sorted(data_dir.rglob('*')):
            if p.is_dir():
                continue

            rel = p.relative_to(data_dir)

            if args.encrypt:
                s3_key = _s3_key(args.prefix, str(rel) + '.enc')
                if args.dry_run:
                    # In dry-run, show planned encrypted upload without requiring encryption
                    upload_file(None, args.bucket, s3_key, p, dry_run=True)
                    success_count += 1
                else:
                    if EncryptionManager is None:
                        failures.append((str(p), "EncryptionManager unavailable"))
                        print(f"Encryption failed for {p}: EncryptionManager unavailable", file=sys.stderr)
                        continue
                    enc_path = staging_dir / (str(rel).replace(os.sep, '_') + '.enc')
                    try:
                        EncryptionManager.encrypt_file(p, password, output_path=enc_path)
                    except Exception as e:
                        failures.append((str(p), f"Encryption failed: {e}"))
                        print(f"Encryption failed for {p}: {e}", file=sys.stderr)
                        continue

                    ok = upload_file(s3, args.bucket, s3_key, enc_path, dry_run=False)
                    if ok:
                        success_count += 1
                    else:
                        failures.append((str(p), f"Upload to s3://{args.bucket}/{s3_key} failed"))
            else:
                s3_key = _s3_key(args.prefix, str(rel))
                ok = upload_file(s3, args.bucket, s3_key, p, dry_run=args.dry_run)
                if ok:
                    success_count += 1
                else:
                    failures.append((str(p), f"Upload to s3://{args.bucket}/{s3_key} failed"))

    if failures:
        print(f"\nS3 sync encountered {len(failures)} failure(s) ({success_count} succeeded):", file=sys.stderr)
        for failed_path, reason in failures:
            print(f"  - {failed_path}: {reason}", file=sys.stderr)
        return 1

    action = "Dry run complete" if args.dry_run else "Sync complete"
    print(f"{action}: {success_count} file(s) processed successfully.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
