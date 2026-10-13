r"""test_profile_manager.py

Tests for profile manager hardening:
- Validate profile names (alphanumeric, dashes, underscores, internal dots)
- Reject traversal segments (.., .)
- Reject absolute paths (/abs, C:\abs)
- Reject path separators (/ and \)
- Reject invalid characters and reserved Windows device names (CON, NUL, etc.)
- Confine operations strictly to data/profiles
- Safe creation and deletion workflows
- Non-zero exit status on validation and command failures
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "tools" / "profiles"))

from profile_manager import (
    validate_profile_name,
    create_profile,
    delete_profile,
    list_profiles,
    get_profiles_dir,
    main as profile_manager_main,
)


@pytest.fixture
def mock_portable_env(tmp_path: Path, monkeypatch):
    """Sets PORTABLE_ROOT to a temporary test directory."""
    monkeypatch.setenv("PORTABLE_ROOT", str(tmp_path))
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = data_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


# -----------------------------------------------------------------------------
# 1. Name Validation Tests
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("valid_name", [
    "personal",
    "work-profile",
    "agent_1",
    "test-123",
    "model.v1",
    "dev_hermes-2",
])
def test_validate_profile_name_valid(mock_portable_env, valid_name):
    """Valid profile names should be accepted."""
    assert validate_profile_name(valid_name) == valid_name


@pytest.mark.parametrize("invalid_name, expected_reason", [
    ("", "empty"),
    ("   ", "empty"),
    ("../escape", "path separators"),
    ("..\\escape", "path separators"),
    ("..", "traversal"),
    (".", "traversal"),
    ("/etc/shadow", "path separators"),
    ("C:\\Windows", "path separators"),
    ("C:autoexec.bat", "absolute"),
    ("foo/bar", "path separators"),
    ("foo\\bar", "path separators"),
    (".hidden", "must start with an alphanumeric"),
    ("trailing.", "must start with an alphanumeric"),
    ("invalid*char", "contain only letters"),
    ("invalid?char", "contain only letters"),
    ("invalid<char", "contain only letters"),
    ("invalid>char", "contain only letters"),
    ("invalid|char", "contain only letters"),
    ("invalid:char", "contain only letters"),
    ("CON", "reserved device name"),
    ("prn", "reserved device name"),
    ("aux", "reserved device name"),
    ("nul", "reserved device name"),
    ("com1", "reserved device name"),
    ("lpt3", "reserved device name"),
])
def test_validate_profile_name_invalid(mock_portable_env, invalid_name, expected_reason):
    """Dangerous or invalid profile names must be rejected with ValueError."""
    with pytest.raises(ValueError, match=expected_reason):
        validate_profile_name(invalid_name)


# -----------------------------------------------------------------------------
# 2. Profile Creation and Deletion Tests
# -----------------------------------------------------------------------------

def test_create_and_delete_profile(mock_portable_env):
    """Create a profile and delete it safely."""
    profiles_dir = get_profiles_dir()

    assert create_profile("research") is True
    target = profiles_dir / "research"
    assert target.is_dir()
    assert (target / "soul.md").exists()

    # Re-creating same profile fails safely
    assert create_profile("research") is False

    # Deleting profile succeeds
    assert delete_profile("research") is True
    assert not target.exists()

    # Deleting non-existent profile fails safely
    assert delete_profile("research") is False


def test_reject_creation_with_traversal(mock_portable_env):
    """create_profile must reject traversal without touching filesystem."""
    data_dir = mock_portable_env / "data"

    with pytest.raises(ValueError):
        create_profile("../../danger")

    assert not (mock_portable_env / "danger").exists()


def test_reject_deletion_with_traversal(mock_portable_env):
    """delete_profile must reject traversal and protect data root."""
    data_dir = mock_portable_env / "data"
    test_file = data_dir / "important.txt"
    test_file.write_text("critical data", encoding="utf-8")

    with pytest.raises(ValueError):
        delete_profile("../data")

    # Important data must still exist
    assert test_file.exists()


# -----------------------------------------------------------------------------
# 3. CLI Command Tests & Exit Status
# -----------------------------------------------------------------------------

def test_profile_cli_create_and_delete(mock_portable_env, capsys):
    """Test CLI commands create, list, and delete with exit codes."""
    # List when empty
    rc = profile_manager_main(["list"])
    assert rc == 0

    # Create profile
    rc = profile_manager_main(["create", "marketing"])
    assert rc == 0
    assert (get_profiles_dir() / "marketing").is_dir()

    # Delete profile
    rc = profile_manager_main(["delete", "marketing"])
    assert rc == 0
    assert not (get_profiles_dir() / "marketing").exists()


def test_profile_cli_rejects_invalid_name_exit_code(mock_portable_env, capsys):
    """CLI must return non-zero exit code when given invalid profile names."""
    rc = profile_manager_main(["create", "../evil"])
    assert rc == 1

    rc = profile_manager_main(["delete", "../evil"])
    assert rc == 1

    rc = profile_manager_main(["create", "CON"])
    assert rc == 1
