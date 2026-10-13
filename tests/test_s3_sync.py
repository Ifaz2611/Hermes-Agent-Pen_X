"""test_s3_sync.py

Tests for S3 sync utility:
- Dry-run shows planned uploads without requiring AWS access or boto3 S3 client
- Dry-run with --encrypt shows .enc target keys without requiring password
- Individual upload and encryption failure reporting with non-zero exit status
- Passphrase resolution from environment variables (HERMES_VAULT_PASSWORD, etc.)
  without requiring command argument exposure
- Non-zero exit status if any upload fails
- Exit 0 when all uploads succeed
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "tools" / "sync"))
sys.path.insert(0, str(repo_root / "src"))

from s3_sync import (
    main as s3_sync_main,
    get_encryption_password,
    _s3_key,
)


@pytest.fixture
def mock_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with mixed files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file1.txt").write_text("content 1", encoding="utf-8")
    (data_dir / "file2.json").write_text('{"key": "value"}', encoding="utf-8")
    sub = data_dir / "subfolder"
    sub.mkdir()
    (sub / "nested.md").write_text("# Nested", encoding="utf-8")
    return data_dir


def test_s3_key_formatting():
    """Verify forward-slash formatting and path sanitization."""
    assert _s3_key("my-prefix", "sub\\nested.txt") == "my-prefix/sub/nested.txt"
    assert _s3_key("", "root.txt") == "root.txt"
    assert _s3_key("prefix/", "path/to/file.dat") == "prefix/path/to/file.dat"


def test_dry_run_offline_without_aws(mock_data_dir: Path, capsys):
    """Dry-run must report planned uploads without requiring AWS access or credentials."""
    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--prefix", "backups/hermes",
        "--data-dir", str(mock_data_dir),
        "--dry-run",
    ])
    assert rc == 0

    captured = capsys.readouterr().out
    assert "[DRY-RUN] Would upload" in captured
    assert "s3://my-test-bucket/backups/hermes/file1.txt" in captured
    assert "s3://my-test-bucket/backups/hermes/file2.json" in captured
    assert "s3://my-test-bucket/backups/hermes/subfolder/nested.md" in captured
    assert "Dry run complete: 3 file(s) processed successfully." in captured


def test_dry_run_with_encrypt(mock_data_dir: Path, capsys):
    """Dry-run with --encrypt must plan .enc uploads without requiring a password."""
    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--data-dir", str(mock_data_dir),
        "--encrypt",
        "--dry-run",
    ])
    assert rc == 0

    captured = capsys.readouterr().out
    assert "s3://my-test-bucket/file1.txt.enc" in captured
    assert "s3://my-test-bucket/file2.json.enc" in captured
    assert "s3://my-test-bucket/subfolder/nested.md.enc" in captured


def test_encrypt_without_password_fails_when_not_dry_run(mock_data_dir: Path, monkeypatch, capsys):
    """--encrypt without password or env var must fail cleanly with code 2."""
    for var in ("HERMES_VAULT_PASSWORD", "HERMES_S3_PASSWORD", "S3_SYNC_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--data-dir", str(mock_data_dir),
        "--encrypt",
    ])
    assert rc == 2

    err = capsys.readouterr().err
    assert "--encrypt requires a passphrase" in err
    assert "HERMES_VAULT_PASSWORD" in err


def test_get_encryption_password_resolution(monkeypatch):
    """Test resolution of encryption passphrase from arguments and environment variables."""
    # From argument
    assert get_encryption_password("ArgPassword", allow_prompt=False) == "ArgPassword"

    # From env var HERMES_VAULT_PASSWORD
    monkeypatch.setenv("HERMES_VAULT_PASSWORD", "EnvPassword1")
    assert get_encryption_password(None, allow_prompt=False) == "EnvPassword1"

    # From env var HERMES_S3_PASSWORD
    monkeypatch.delenv("HERMES_VAULT_PASSWORD")
    monkeypatch.setenv("HERMES_S3_PASSWORD", "EnvPassword2")
    assert get_encryption_password(None, allow_prompt=False) == "EnvPassword2"


def test_upload_individual_failure_reporting(mock_data_dir: Path, monkeypatch, capsys):
    """When an upload fails, individual failures must be reported and return non-zero exit status."""
    class MockS3Client:
        def upload_file(self, local_path, bucket, key):
            if "file2" in key:
                from botocore.exceptions import ClientError
                raise ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "PutObject")
            return None

    monkeypatch.setattr("s3_sync.s3_client", lambda profile=None: MockS3Client())

    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--data-dir", str(mock_data_dir),
    ])
    # Must exit with non-zero status
    assert rc == 1

    err = capsys.readouterr().err
    assert "S3 sync encountered 1 failure(s)" in err
    assert "file2.json" in err


def test_encryption_failure_reporting(mock_data_dir: Path, monkeypatch, capsys):
    """When encryption fails on a file, report the individual failure and return non-zero exit status."""
    class MockS3Client:
        def upload_file(self, local_path, bucket, key):
            return None

    monkeypatch.setattr("s3_sync.s3_client", lambda profile=None: MockS3Client())
    monkeypatch.setenv("HERMES_VAULT_PASSWORD", "Pass123456")

    # Simulate encryption failure on file1
    from security.crypto import EncryptionManager
    orig_encrypt_file = EncryptionManager.encrypt_file

    def mock_encrypt(input_path, password, output_path=None):
        if "file1" in str(input_path):
            raise ValueError("Corrupt file content")
        return orig_encrypt_file(input_path, password, output_path=output_path)

    monkeypatch.setattr("security.crypto.EncryptionManager.encrypt_file", staticmethod(mock_encrypt))

    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--data-dir", str(mock_data_dir),
        "--encrypt",
    ])
    assert rc == 1

    err = capsys.readouterr().err
    assert "S3 sync encountered 1 failure(s)" in err
    assert "file1.txt" in err
    assert "Encryption failed: Corrupt file content" in err


def test_all_uploads_succeed(mock_data_dir: Path, monkeypatch, capsys):
    """When all uploads succeed, return exit code 0."""
    class MockS3Client:
        def upload_file(self, local_path, bucket, key):
            return None

    monkeypatch.setattr("s3_sync.s3_client", lambda profile=None: MockS3Client())

    rc = s3_sync_main([
        "--bucket", "my-test-bucket",
        "--data-dir", str(mock_data_dir),
    ])
    assert rc == 0

    out = capsys.readouterr().out
    assert "Sync complete: 3 file(s) processed successfully." in out
