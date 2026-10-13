"""Tests for backup and restore manager."""

import json
import os
import tempfile
from pathlib import Path
import pytest

from tools.backup.backup_manager import (
    create_backup,
    verify_backup,
    restore_backup,
    detect_encrypted_vault_files,
    compute_file_sha256,
)


class TestBackupRestore:
    def test_backup_and_restore_cycle(self, tmp_path):
        source = tmp_path / "data"
        source.mkdir()
        (source / "subdir").mkdir()
        
        file1 = source / "config.yaml"
        file1.write_text("model: test-model\n", encoding="utf-8")
        
        file2 = source / "subdir" / "session.json"
        file2.write_text('{"messages": ["hello"]}', encoding="utf-8")
        
        # 1. Create backup with custom destination
        dest_zip = tmp_path / "custom_backup.zip"
        rc, out_path, manifest = create_backup(source_dir=source, dest_path=dest_zip)
        
        assert rc == 0
        assert out_path == dest_zip
        assert dest_zip.is_file()
        assert manifest["total_files"] == 2
        assert "config.yaml" in manifest["files"]
        assert "subdir/session.json" in manifest["files"]
        
        # 2. Verify backup
        ok, msg, m = verify_backup(dest_zip)
        assert ok
        assert "Verified all 2 files" in msg
        
        # 3. Restore to new location
        restore_dir = tmp_path / "restored_data"
        rc_res = restore_backup(backup_path=dest_zip, dest_dir=restore_dir)
        
        assert rc_res == 0
        assert (restore_dir / "config.yaml").read_text(encoding="utf-8") == "model: test-model\n"
        assert (restore_dir / "subdir" / "session.json").read_text(encoding="utf-8") == '{"messages": ["hello"]}'

    def test_backup_directory_destination(self, tmp_path):
        source = tmp_path / "data"
        source.mkdir()
        (source / "a" / "b").mkdir(parents=True)
        (source / "a" / "b" / "deep.txt").write_text("deep relative path", encoding="utf-8")
        
        dest_dir = tmp_path / "backup_folder"
        rc, out_path, manifest = create_backup(source_dir=source, dest_path=dest_dir)
        
        assert rc == 0
        assert (dest_dir / "backup_manifest.json").is_file()
        assert (dest_dir / "README_SECURITY.txt").is_file()
        assert (dest_dir / "data" / "a" / "b" / "deep.txt").read_text(encoding="utf-8") == "deep relative path"
        
        # Verify and restore from directory backup
        ok, msg, _ = verify_backup(dest_dir)
        assert ok
        
        target = tmp_path / "restored_dir"
        rc_res = restore_backup(backup_path=dest_dir, dest_dir=target)
        assert rc_res == 0
        assert (target / "a" / "b" / "deep.txt").read_text(encoding="utf-8") == "deep relative path"

    def test_tampered_backup_fails_verification(self, tmp_path):
        source = tmp_path / "data"
        source.mkdir()
        (source / "file.txt").write_text("original content", encoding="utf-8")
        
        dest_dir = tmp_path / "tampered_folder"
        create_backup(source_dir=source, dest_path=dest_dir)
        
        # Tamper with the backed-up file
        (dest_dir / "data" / "file.txt").write_text("tampered content", encoding="utf-8")
        
        ok, msg, _ = verify_backup(dest_dir)
        assert not ok
        assert "Checksum mismatch" in msg
        
        # Restore should be aborted
        target = tmp_path / "tampered_restore"
        rc_res = restore_backup(backup_path=dest_dir, dest_dir=target)
        assert rc_res != 0

    def test_detect_vault_encrypted_files(self, tmp_path):
        source = tmp_path / "data"
        source.mkdir()
        (source / "plain.txt").write_text("plaintext", encoding="utf-8")
        
        vault_envelope = json.dumps({
            "vault_version": 1,
            "ciphertext": "gAAAAABl...",
            "salt": "abc"
        })
        (source / "secrets.env").write_text(vault_envelope, encoding="utf-8")
        
        enc_files = detect_encrypted_vault_files(source)
        assert "secrets.env" in enc_files
        assert "plain.txt" not in enc_files
