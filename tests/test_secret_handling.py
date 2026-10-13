"""test_secret_handling.py

Tests for secret handling across utilities:
- Avoid requiring passwords in command arguments
- Test that logs and console outputs never include secret values
- Test that health reports and logs do not expose plaintext credentials
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root / "tools" / "mcp"))
sys.path.insert(0, str(repo_root / "tools" / "sync"))
sys.path.insert(0, str(repo_root / "tools" / "doctor"))

from security.cli import main as security_cli_main
from s3_sync import main as s3_sync_main
from mcp_manager import main as mcp_manager_main
from export_health import collect as collect_health


SECRET_PASSWORD = "SuperSecretPassword999!"
API_KEY_VALUE = "sk-live-secret-key-123456789"


def test_security_cli_never_logs_secret_password(tmp_path: Path, monkeypatch, capsys):
    """Verify that encrypting/decrypting does not print the secret password to stdout or stderr."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / ".env").write_text(f"KEY={API_KEY_VALUE}", encoding="utf-8")

    monkeypatch.setenv("HERMES_VAULT_PASSWORD", SECRET_PASSWORD)

    # 1. Encrypt
    rc = security_cli_main(["encrypt", str(vault_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert SECRET_PASSWORD not in captured.out
    assert SECRET_PASSWORD not in captured.err

    # 2. Status
    rc = security_cli_main(["status", str(vault_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert SECRET_PASSWORD not in captured.out
    assert SECRET_PASSWORD not in captured.err

    # 3. Decrypt
    rc = security_cli_main(["decrypt", str(vault_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert SECRET_PASSWORD not in captured.out
    assert SECRET_PASSWORD not in captured.err


def test_s3_sync_never_logs_secret_password(tmp_path: Path, monkeypatch, capsys):
    """Verify that s3_sync does not print the secret password to stdout or stderr."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "file.txt").write_text("content", encoding="utf-8")

    monkeypatch.setenv("HERMES_VAULT_PASSWORD", SECRET_PASSWORD)

    rc = s3_sync_main([
        "--bucket", "test-bucket",
        "--data-dir", str(data_dir),
        "--encrypt",
        "--dry-run",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert SECRET_PASSWORD not in captured.out
    assert SECRET_PASSWORD not in captured.err


def test_mcp_manager_does_not_leak_env_secrets_in_list(tmp_path: Path, monkeypatch, capsys):
    """Verify that mcp_manager list command does not print env variables / API keys."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Add server with sensitive environment variable
    rc = mcp_manager_main([
        "add", "my-server",
        "--cmd", "node",
        "--env", f"API_KEY={API_KEY_VALUE}", "SECRET_TOKEN=xyz123",
        "--args", "server.js",
    ])
    captured = capsys.readouterr()
    assert API_KEY_VALUE not in captured.out
    assert API_KEY_VALUE not in captured.err

    # List servers
    rc = mcp_manager_main(["list"])
    captured = capsys.readouterr()
    assert "my-server" in captured.out
    assert API_KEY_VALUE not in captured.out
    assert "xyz123" not in captured.out


def test_mcp_manager_malformed_env_does_not_echo_secret(tmp_path: Path, monkeypatch, capsys):
    """Verify that malformed env entry does not echo the input token."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Malformed entry without =
    rc = mcp_manager_main([
        "add", "test-server",
        "--cmd", "node",
        "--env", f"SECRET_WITHOUT_EQUALS_{API_KEY_VALUE}",
        "--args", "server.js",
    ])
    captured = capsys.readouterr()
    assert API_KEY_VALUE not in captured.out
    assert API_KEY_VALUE not in captured.err


def test_health_report_does_not_expose_unlocked_vault_secrets(tmp_path: Path):
    """Verify health collector collects only metadata and no secrets."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / ".env").write_text(f"SECRET_KEY={API_KEY_VALUE}", encoding="utf-8")

    report = collect_health(data_dir)
    report_json = json.dumps(report)
    assert API_KEY_VALUE not in report_json
