"""Tests for upgrade and rollback manager."""

import json
from pathlib import Path
import pytest

from tools.upgrade.upgrade_manager import (
    plan_upgrade,
    create_metadata_backup,
    execute_rollback,
    read_source_state,
)


class TestUpgradeManager:
    def test_plan_upgrade_preview(self, tmp_path):
        repo = tmp_path / "hermes_repo"
        repo.mkdir()
        runtime_dir = repo / ".cache" / "runtimes" / "windows-x64"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "manifest.json").write_text(json.dumps({
            "versions": {
                "python": "3.11.10+20241016",
                "node": "22.14.0",
                "uv": "0.6.8",
                "rg": "14.1.1"
            }
        }), encoding="utf-8")
        
        plan = plan_upgrade(repo, runtime_dir)
        assert "changes" in plan
        assert len(plan["changes"]) >= 5
        assert any(c["component"] == "Hermes Source" for c in plan["changes"])

    def test_backup_and_rollback(self, tmp_path):
        repo = tmp_path / "hermes_repo"
        repo.mkdir()
        runtime_dir = repo / ".cache" / "runtimes" / "windows-x64"
        runtime_dir.mkdir(parents=True)
        
        original_manifest = {
            "versions": {"python": "3.11.10+20241016", "hermes": "commit-123"}
        }
        manifest_file = runtime_dir / "manifest.json"
        manifest_file.write_text(json.dumps(original_manifest), encoding="utf-8")
        
        # Create metadata backup snapshot
        backup_dir = create_metadata_backup(repo, runtime_dir)
        assert backup_dir.is_dir()
        assert (backup_dir / "manifest.json").is_file()
        assert (backup_dir / "rollback_descriptor.json").is_file()
        
        # Simulate an upgrade mutating manifest.json
        mutated_manifest = {
            "versions": {"python": "3.11.10+20241016", "hermes": "mutated-456"}
        }
        manifest_file.write_text(json.dumps(mutated_manifest), encoding="utf-8")
        
        # Perform rollback
        rc = execute_rollback(repo, runtime_dir, custom_backup_dir=backup_dir)
        assert rc == 0
        
        # Verify restored manifest matches original snapshot
        restored = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert restored["versions"]["hermes"] == "commit-123"
