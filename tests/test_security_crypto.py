"""test_security_crypto.py

Automated tests for the security module:
- Encrypt/decrypt round trips (raw data and files)
- Wrong passwords (fails and preserves original data)
- Already-encrypted files (no double encryption or corruption)
- Plaintext files on decrypt (no corruption)
- Mixed vault contents (sensitive files encrypted, non-sensitive untouched)
- Atomic file writes
- Transactional backups and rollback on failure without changing original data
- Interrupted operation recovery (process stopped partway through)
- Hardware token options/metadata removal from vault
- CLI command integration (encrypt, decrypt, recover, status)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import pytest

# Ensure src is on sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from security.crypto import (
    DataVault,
    EncryptionManager,
    VaultBackupManager,
    VAULT_FILENAME,
    VAULT_BACKUP_DIR,
    VAULT_MARKER,
    is_file_encrypted,
    _atomic_write_bytes,
    _atomic_write_text,
)
from security.cli import main as security_cli_main


PASSWORD = "TestPassword123!"
WRONG_PASSWORD = "WrongPassword999!"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture providing a clean temporary directory."""
    return tmp_path


# -----------------------------------------------------------------------------
# 1. Round-Trip Tests (Data & Files)
# -----------------------------------------------------------------------------

def test_encrypt_decrypt_data_round_trip():
    """Verify encryption and decryption round trip for raw bytes."""
    raw = b"Secret payload with binary: \x00\xff\xfe\x01 and unicode: \xf0\x9f\x94\x90"
    encrypted = EncryptionManager.encrypt_data(raw, PASSWORD)

    assert "salt" in encrypted
    assert "token" in encrypted

    decrypted = EncryptionManager.decrypt_data(encrypted, PASSWORD)
    assert decrypted == raw


def test_encrypt_decrypt_file_round_trip(temp_dir: Path):
    """Verify in-place and out-of-place file encryption and decryption round trips."""
    fpath = temp_dir / "secret.env"
    original_data = b"OPENAI_API_KEY=sk-test-1234567890\nDB_PASS=supersecret\n"
    fpath.write_bytes(original_data)

    # In-place encryption
    enc_path = EncryptionManager.encrypt_file(fpath, PASSWORD)
    assert enc_path == fpath
    assert is_file_encrypted(fpath)

    # Verify envelope format
    env = json.loads(fpath.read_text(encoding="utf-8"))
    assert env[VAULT_MARKER] == 1
    assert env["original_name"] == "secret.env"

    # In-place decryption
    dec_path = EncryptionManager.decrypt_file(fpath, PASSWORD)
    assert dec_path == fpath
    assert not is_file_encrypted(fpath)
    assert fpath.read_bytes() == original_data

    # Out-of-place encryption and decryption
    out_enc = temp_dir / "secret.enc"
    EncryptionManager.encrypt_file(fpath, PASSWORD, output_path=out_enc)
    assert is_file_encrypted(out_enc)
    assert not is_file_encrypted(fpath)  # source remains plaintext

    out_dec = temp_dir / "secret.restored"
    EncryptionManager.decrypt_file(out_enc, PASSWORD, output_path=out_dec)
    assert out_dec.read_bytes() == original_data


def test_empty_file_round_trip(temp_dir: Path):
    """Verify that empty files encrypt and decrypt accurately."""
    empty_file = temp_dir / "empty.txt"
    empty_file.write_bytes(b"")

    EncryptionManager.encrypt_file(empty_file, PASSWORD)
    assert is_file_encrypted(empty_file)

    EncryptionManager.decrypt_file(empty_file, PASSWORD)
    assert empty_file.read_bytes() == b""


# -----------------------------------------------------------------------------
# 2. Wrong Password Tests
# -----------------------------------------------------------------------------

def test_decrypt_data_wrong_password():
    """Verify that decrypting data with wrong password raises an exception."""
    raw = b"sensitive credentials"
    encrypted = EncryptionManager.encrypt_data(raw, PASSWORD)

    with pytest.raises(Exception):
        EncryptionManager.decrypt_data(encrypted, WRONG_PASSWORD)


def test_decrypt_file_wrong_password_preserves_content(temp_dir: Path):
    """Verify decrypt_file with wrong password fails and leaves file unchanged."""
    fpath = temp_dir / ".env"
    fpath.write_bytes(b"SECRET_KEY=123")
    EncryptionManager.encrypt_file(fpath, PASSWORD)
    encrypted_bytes = fpath.read_bytes()

    with pytest.raises(Exception):
        EncryptionManager.decrypt_file(fpath, WRONG_PASSWORD)

    # Original encrypted file must NOT be changed or corrupted
    assert fpath.read_bytes() == encrypted_bytes
    assert is_file_encrypted(fpath)


# -----------------------------------------------------------------------------
# 3. Already-Encrypted and Already-Plaintext Files
# -----------------------------------------------------------------------------

def test_encrypt_already_encrypted_file(temp_dir: Path):
    """Encrypting an already encrypted file must not double-encrypt or corrupt it."""
    fpath = temp_dir / "config.yaml"
    raw = b"model: gpt-4\n"
    fpath.write_bytes(raw)

    EncryptionManager.encrypt_file(fpath, PASSWORD)
    first_encrypted = fpath.read_bytes()

    # Second call
    EncryptionManager.encrypt_file(fpath, PASSWORD)
    assert fpath.read_bytes() == first_encrypted

    # Decrypt should yield original plaintext
    EncryptionManager.decrypt_file(fpath, PASSWORD)
    assert fpath.read_bytes() == raw


def test_decrypt_already_plaintext_file(temp_dir: Path):
    """Decrypting a plaintext file returns the file untouched."""
    fpath = temp_dir / "config.yaml"
    raw = b"model: gpt-4\n"
    fpath.write_bytes(raw)

    EncryptionManager.decrypt_file(fpath, PASSWORD)
    assert fpath.read_bytes() == raw


# -----------------------------------------------------------------------------
# 4. Mixed Vault Contents
# -----------------------------------------------------------------------------

def test_vault_mixed_contents(temp_dir: Path):
    """Verify DataVault encrypts ONLY sensitive files and leaves non-sensitive files untouched."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()

    # Sensitive files
    env_file = vault_root / ".env"
    env_file.write_text("API_KEY=xyz", encoding="utf-8")

    cfg_file = vault_root / "config.yaml"
    cfg_file.write_text("provider: anthropic", encoding="utf-8")

    sessions_dir = vault_root / "sessions"
    sessions_dir.mkdir()
    chat_file = sessions_dir / "session1.json"
    chat_file.write_text('{"messages": ["hello"]}', encoding="utf-8")

    memory_dir = vault_root / "memory"
    memory_dir.mkdir()
    mem_file = memory_dir / "knowledge.md"
    mem_file.write_text("# Notes", encoding="utf-8")

    # Non-sensitive files
    readme = vault_root / "README.md"
    readme.write_text("Public docs", encoding="utf-8")

    cache_dir = vault_root / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "temp.dat"
    cache_file.write_bytes(b"cached data")

    vault = DataVault(vault_root, password=PASSWORD)
    assert not vault.is_encrypted()

    # Lock vault
    result = vault.lock()
    assert result["newly_encrypted"] == 4
    assert vault.is_encrypted()

    # Verify sensitive files are encrypted
    assert is_file_encrypted(env_file)
    assert is_file_encrypted(cfg_file)
    assert is_file_encrypted(chat_file)
    assert is_file_encrypted(mem_file)

    # Verify non-sensitive files remain plaintext
    assert not is_file_encrypted(readme)
    assert readme.read_text(encoding="utf-8") == "Public docs"
    assert not is_file_encrypted(cache_file)
    assert cache_file.read_bytes() == b"cached data"

    # Unlock vault
    unlock_res = vault.unlock(password=PASSWORD)
    assert unlock_res["decrypted_files"] == 4
    assert not vault.is_encrypted()

    # Verify all sensitive files restored
    assert env_file.read_text(encoding="utf-8") == "API_KEY=xyz"
    assert cfg_file.read_text(encoding="utf-8") == "provider: anthropic"
    assert chat_file.read_text(encoding="utf-8") == '{"messages": ["hello"]}'
    assert mem_file.read_text(encoding="utf-8") == "# Notes"


# -----------------------------------------------------------------------------
# 5. Failures Without Changing Original Data & Rollback
# -----------------------------------------------------------------------------

def test_vault_unlock_wrong_password_rollback(temp_dir: Path):
    """Wrong password on unlock rolls back any changes and preserves encrypted files intact."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()

    f1 = vault_root / ".env"
    f1.write_text("SECRET=1", encoding="utf-8")
    f2 = vault_root / "config.yaml"
    f2.write_text("SECRET=2", encoding="utf-8")

    vault = DataVault(vault_root, password=PASSWORD)
    vault.lock()

    f1_enc_before = f1.read_bytes()
    f2_enc_before = f2.read_bytes()

    # Attempt unlock with wrong password
    with pytest.raises(ValueError, match="Failed to decrypt"):
        vault.unlock(password=WRONG_PASSWORD)

    # Both files must remain encrypted and unchanged
    assert f1.read_bytes() == f1_enc_before
    assert f2.read_bytes() == f2_enc_before
    assert is_file_encrypted(f1)
    assert is_file_encrypted(f2)
    assert vault.is_encrypted()


def test_vault_lock_failure_rollback(temp_dir: Path, monkeypatch):
    """Simulated failure during lock rolls back all files to plaintext."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()

    f1 = vault_root / ".env"
    f1.write_text("SECRET=1", encoding="utf-8")
    f2 = vault_root / "config.yaml"
    f2.write_text("SECRET=2", encoding="utf-8")

    vault = DataVault(vault_root, password=PASSWORD)

    original_encrypt_file = EncryptionManager.encrypt_file
    call_count = 0

    def mock_encrypt(input_path, password, output_path=None):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise OSError("Simulated disk error during encryption")
        return original_encrypt_file(input_path, password, output_path=output_path)

    monkeypatch.setattr(EncryptionManager, "encrypt_file", mock_encrypt)

    with pytest.raises(OSError, match="Simulated disk error"):
        vault.lock()

    # Both files must be restored to original plaintext
    assert f1.read_text(encoding="utf-8") == "SECRET=1"
    assert f2.read_text(encoding="utf-8") == "SECRET=2"
    assert not is_file_encrypted(f1)
    assert not is_file_encrypted(f2)
    assert not vault.is_encrypted()


# -----------------------------------------------------------------------------
# 6. Interrupted Operation Recovery (Process Stops Partway Through)
# -----------------------------------------------------------------------------

def test_interrupted_operation_recovery(temp_dir: Path, monkeypatch):
    """Verify that when a process stops partway through, backups are preserved and recover() restores state."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()

    f1 = vault_root / ".env"
    f1.write_text("ORIGINAL_ENV", encoding="utf-8")
    f2 = vault_root / "config.yaml"
    f2.write_text("ORIGINAL_CONFIG", encoding="utf-8")

    vault = DataVault(vault_root, password=PASSWORD)

    # Simulate crash midway through lock:
    # We create a backup, partially encrypt f1, and simulate process termination before commit/rollback
    cfg = vault._read_config()
    targets = [f1, f2]
    vault._backup_mgr.create_backup("lock", targets, cfg)

    # File 1 was encrypted, file 2 not yet, then process stopped
    EncryptionManager.encrypt_file(f1, PASSWORD)

    # Verify state before recovery: vault is inconsistent
    assert vault.has_pending_recovery()
    status = vault.get_vault_status()
    assert status["pending_recovery"] is True

    # Re-instantiate DataVault (simulating new process invocation)
    recovered_vault = DataVault(vault_root)
    assert recovered_vault.has_pending_recovery()

    # Execute recovery
    rec_res = recovered_vault.recover()
    assert rec_res["recovered"] is True
    assert rec_res["recovered_files"] == 2

    # Files must be restored to original states
    assert f1.read_text(encoding="utf-8") == "ORIGINAL_ENV"
    assert f2.read_text(encoding="utf-8") == "ORIGINAL_CONFIG"
    assert not is_file_encrypted(f1)
    assert not is_file_encrypted(f2)
    assert not recovered_vault.has_pending_recovery()


# -----------------------------------------------------------------------------
# 7. Hardware Token Option Removal
# -----------------------------------------------------------------------------

def test_hardware_token_metadata_not_in_vault(temp_dir: Path):
    """Verify hardware-token metadata is not stored in .vault config or reported in status."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()
    (vault_root / ".env").write_text("SECRET=1", encoding="utf-8")

    vault = DataVault(vault_root, password=PASSWORD)
    vault.lock()

    cfg = json.loads((vault_root / VAULT_FILENAME).read_text(encoding="utf-8"))
    assert "hardware_token" not in cfg

    st = vault.get_vault_status()
    assert "hardware_token_enabled" not in st


# -----------------------------------------------------------------------------
# 8. Security CLI Integration & Environment Variable Password
# -----------------------------------------------------------------------------

def test_security_cli_encrypt_decrypt_recover(temp_dir: Path, monkeypatch):
    """Test security CLI encrypt, status, decrypt, and recover commands."""
    vault_root = temp_dir / "vault"
    vault_root.mkdir()
    (vault_root / ".env").write_text("ENV_KEY=abc", encoding="utf-8")

    # Use HERMES_VAULT_PASSWORD environment variable
    monkeypatch.setenv("HERMES_VAULT_PASSWORD", PASSWORD)

    # 1. Encrypt via CLI
    rc = security_cli_main(["encrypt", str(vault_root)])
    assert rc == 0
    assert is_file_encrypted(vault_root / ".env")

    # 2. Status via CLI
    rc = security_cli_main(["status", str(vault_root)])
    assert rc == 0

    # 3. Decrypt via CLI
    rc = security_cli_main(["decrypt", str(vault_root)])
    assert rc == 0
    assert not is_file_encrypted(vault_root / ".env")
    assert (vault_root / ".env").read_text(encoding="utf-8") == "ENV_KEY=abc"

    # 4. Recover via CLI when no pending recovery
    rc = security_cli_main(["recover", str(vault_root)])
    assert rc == 0
