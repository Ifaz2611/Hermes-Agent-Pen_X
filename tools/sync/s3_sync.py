"""s3_sync.py

Sync the data/ folder to AWS S3 with optional end-to-end encryption using the repo's
EncryptionManager (PBKDF2 + Fernet). Designed as a minimal, auditable tool — adjust for
production (retries, parallelism, multipart uploads) as needed.

Usage:
  python tools\sync\s3_sync.py --bucket my-bucket --prefix hermes-backup --encrypt --password "passphrase"

Notes:
- Requires boto3 installed (pip install boto3)
- Encryption uses src/security/crypto.py EncryptionManager to create .enc JSON files and uploads those.
"""
import argparse
import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import tempfile
import shutil
import sys

# Import repository encryption utilities
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root / 'src'))

try:
    from security.crypto import EncryptionManager
except Exception as e:
    print(f"Failed to import EncryptionManager: {e}")
    raise


def parse_args():
    p = argparse.ArgumentParser(description='Sync data/ to S3 with optional E2EE')
    p.add_argument('--bucket', required=True, help='S3 bucket name')
    p.add_argument('--prefix', default='', help='S3 key prefix')
    p.add_argument('--data-dir', default=str(repo_root / 'data'), help='Local data directory')
    p.add_argument('--encrypt', action='store_true', help='Encrypt files before upload')
    p.add_argument('--password', help='Passphrase for encryption (required if --encrypt)')
    p.add_argument('--aws-profile', help='AWS CLI profile to use')
    p.add_argument('--dry-run', action='store_true', help='Show what would be uploaded')
    return p.parse_args()


def s3_client(profile=None):
    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client('s3')
    return boto3.client('s3')


def upload_file(s3, bucket, key, local_path, dry_run=False):
    print(f"Uploading {local_path} -> s3://{bucket}/{key}")
    if dry_run:
        return True
    try:
        s3.upload_file(str(local_path), bucket, key)
        return True
    except ClientError as e:
        print(f"Upload failed: {e}")
        return False


def main():
    args = parse_args()

    if args.encrypt and not args.password:
        print("--password is required when --encrypt is used")
        return 2

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return 2

    s3 = s3_client(args.aws_profile)

    # Use a temporary staging dir for encrypted files
    with tempfile.TemporaryDirectory() as staging:
        staging = Path(staging)
        for p in sorted(data_dir.rglob('*')):
            if p.is_dir():
                continue

            # Compute relative key
            rel = p.relative_to(data_dir)
            # Decide whether to upload raw or encrypted file
            if args.encrypt:
                # create encrypted JSON file in staging
                enc_path = staging / (str(rel).replace(os.sep, '_') + '.enc')
                try:
                    EncryptionManager.encrypt_file(p, args.password, output_path=enc_path)
                except Exception as e:
                    print(f"Encryption failed for {p}: {e}")
                    continue
                s3_key = os.path.join(args.prefix, str(rel) + '.enc').lstrip('/\\')
                upload_file(s3, args.bucket, s3_key, enc_path, dry_run=args.dry_run)
            else:
                s3_key = os.path.join(args.prefix, str(rel)).lstrip('/\\')
                upload_file(s3, args.bucket, s3_key, p, dry_run=args.dry_run)

    print("Sync complete")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
