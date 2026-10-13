"""Tests for diagnostics utility."""

import json
from pathlib import Path
import pytest

from tools.doctor.diagnostics import (
    detect_platform_info,
    inspect_runtimes,
    inspect_virtual_env,
    inspect_source_checkout,
    inspect_data_path,
    inspect_optional_dependencies,
    run_diagnostics,
)


class TestDiagnostics:
    def test_detect_platform_info(self):
        info = detect_platform_info()
        assert "os" in info
        assert "arch" in info
        assert isinstance(info["supported"], bool)
        assert info["status"] in ("PASS", "FAIL")

    def test_run_diagnostics_structure(self, tmp_path):
        # Create a mock repo directory structure
        repo = tmp_path / "mock_repo"
        repo.mkdir()
        (repo / "data").mkdir()
        (repo / "src" / "hermes-agent").mkdir(parents=True)
        (repo / "src" / "security").mkdir(parents=True)
        
        diag = run_diagnostics(root=repo)
        assert "overall_status" in diag
        assert "summary" in diag
        assert "platform" in diag
        assert "runtimes" in diag
        assert "virtual_environment" in diag
        assert "source_checkout" in diag
        assert "data_path" in diag
        assert "optional_dependencies" in diag
        
        assert diag["source_checkout"]["exists"] is True
        assert diag["source_checkout"]["security_package_exists"] is True
        assert diag["data_path"]["exists"] is True

    def test_diagnostics_does_not_modify_user_data(self, tmp_path):
        data_dir = tmp_path / "user_data"
        data_dir.mkdir()
        test_file = data_dir / "user_secrets.txt"
        test_file.write_text("precious user data", encoding="utf-8")
        
        before_files = set(data_dir.rglob("*"))
        before_stat = test_file.stat()
        
        diag = inspect_data_path(root=tmp_path, custom_data_dir=data_dir)
        
        after_files = set(data_dir.rglob("*"))
        after_stat = test_file.stat()
        
        # Strictly verify no files were created, removed, or modified
        assert before_files == after_files
        assert before_stat.st_mtime == after_stat.st_mtime
        assert before_stat.st_size == after_stat.st_size
        assert test_file.read_text(encoding="utf-8") == "precious user data"
        assert diag["readable"] is True
