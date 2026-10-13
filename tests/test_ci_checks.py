"""Tests for CI checks and repository integrity."""

from pathlib import Path
import pytest

from scripts.ci_check import (
    check_python_files,
    check_shell_files,
    check_powershell_and_batch_files,
    check_javascript_files,
    check_markdown_links,
    check_tracked_files_hygiene,
    find_repo_root,
)


class TestCIChecks:
    @pytest.fixture
    def repo_root(self):
        return find_repo_root()

    def test_python_files_syntax(self, repo_root):
        ok, errors = check_python_files(repo_root)
        assert ok, f"Python compilation errors: {errors}"

    def test_shell_files_syntax(self, repo_root):
        ok, errors = check_shell_files(repo_root)
        assert ok, f"Shell syntax errors: {errors}"

    def test_powershell_and_batch_files_syntax(self, repo_root):
        ok, errors = check_powershell_and_batch_files(repo_root)
        assert ok, f"PowerShell/Batch syntax errors: {errors}"

    def test_javascript_files_syntax(self, repo_root):
        ok, errors = check_javascript_files(repo_root)
        assert ok, f"JavaScript syntax errors: {errors}"

    def test_markdown_relative_links(self, repo_root):
        ok, errors = check_markdown_links(repo_root)
        assert ok, f"Broken markdown links: {errors}"

    def test_tracked_files_hygiene(self, repo_root):
        ok, errors = check_tracked_files_hygiene(repo_root)
        assert ok, f"Untracked hygiene violations (secrets, downloads, or generated files tracked): {errors}"
