"""Tests for P3 retention + conflict handling (preview, no silent overwrites)."""

import time
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from tools.backup.backup_manager import (
    create_backup,
    verify_backup,
    restore_backup,
    preview_restore,
    list_backups,
    prune_backups,
)


def _make_source(tmp_path: Path, name="data", files=None) -> Path:
    src = tmp_path / name
    src.mkdir(parents=True, exist_ok=True)
    for rel, content in (files or {"a.txt": "v1"}).items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return src


class TestRetention:
    def test_prune_dry_run_keeps_newest(self, tmp_path, capsys):
        bdir = tmp_path / "backups"
        bdir.mkdir()
        # Create 4 fake backups with increasing mtime.
        for i in range(4):
            src = _make_source(tmp_path / f"s{i}", name="data", files={f"f{i}.txt": "x"})
            dest = bdir / f"hermes_backup_2024010{i}_000000.zip"
            rc, _, _ = create_backup(source_dir=src, dest_path=dest, repo_root=tmp_path)
            assert rc == 0
            # Ensure mtime ordering.
            time.sleep(0.02)
        assert len(list_backups(bdir)) == 4
        rc, msg, details = prune_backups(bdir, keep_last_n=2, dry_run=True)
        assert rc == 0
        assert len(details["to_delete"]) == 2
        assert len(details["kept"]) == 2
        assert len(list(list_backups(bdir))) == 4  # dry-run deletes nothing
        out = capsys.readouterr().out
        assert "Retention preview" in out

    def test_prune_real_deletes_oldest(self, tmp_path):
        bdir = tmp_path / "backups"
        bdir.mkdir()
        for i in range(3):
            src = _make_source(tmp_path / f"s{i}", name="data", files={"a.txt": f"v{i}"})
            dest = bdir / f"hermes_backup_2024010{i}_000000.zip"
            create_backup(source_dir=src, dest_path=dest, repo_root=tmp_path)
            time.sleep(0.02)
        rc, msg, details = prune_backups(bdir, keep_last_n=1, dry_run=False)
        assert rc == 0
        remaining = list_backups(bdir)
        assert len(remaining) == 1
        assert "20240102" in remaining[0].name

    def test_prune_keep_all_when_fewer(self, tmp_path):
        bdir = tmp_path / "backups"
        bdir.mkdir()
        src = _make_source(tmp_path / "s", name="data")
        dest = bdir / "hermes_backup_20240101_000000.zip"
        create_backup(source_dir=src, dest_path=dest, repo_root=tmp_path)
        rc, msg, details = prune_backups(bdir, keep_last_n=5, dry_run=False)
        assert rc == 0
        assert len(list_backups(bdir)) == 1


class TestRestoreConflicts:
    def _backup(self, tmp_path: Path, content="original") -> Path:
        src = _make_source(tmp_path / "src", name="data", files={"a.txt": content})
        dest = tmp_path / "b.zip"
        rc, _, _ = create_backup(source_dir=src, dest_path=dest, repo_root=tmp_path)
        assert rc == 0
        return dest

    def test_preview_detects_conflict(self, tmp_path):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("DIFFERENT local edit", encoding="utf-8")
        prev = preview_restore(b, dest)
        assert prev["valid"] is True
        assert len(prev["conflicts"]) == 1
        assert prev["conflicts"][0]["path"] == "a.txt"

    def test_default_fail_aborts_on_conflict(self, tmp_path, capsys):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("local edit", encoding="utf-8")
        rc = restore_backup(backup_path=b, dest_dir=dest, dry_run=False)
        assert rc != 0
        # Existing file preserved (no silent overwrite).
        assert (dest / "a.txt").read_text(encoding="utf-8") == "local edit"

    def test_dry_run_previews_conflict_without_modifying(self, tmp_path, capsys):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("local edit", encoding="utf-8")
        rc = restore_backup(backup_path=b, dest_dir=dest, dry_run=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "CONFLICT" in out
        assert (dest / "a.txt").read_text(encoding="utf-8") == "local edit"

    def test_skip_preserves_existing(self, tmp_path):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("keep me", encoding="utf-8")
        rc = restore_backup(backup_path=b, dest_dir=dest, dry_run=False,
                            overwrite_policy="skip")
        assert rc == 0
        assert (dest / "a.txt").read_text(encoding="utf-8") == "keep me"

    def test_overwrite_replaces_after_preview(self, tmp_path):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("old", encoding="utf-8")
        rc = restore_backup(backup_path=b, dest_dir=dest, dry_run=False,
                            overwrite_policy="overwrite")
        assert rc == 0
        assert (dest / "a.txt").read_text(encoding="utf-8") == "original"

    def test_keep_both_never_overwrites(self, tmp_path):
        b = self._backup(tmp_path, "original")
        dest = tmp_path / "restored"
        dest.mkdir()
        (dest / "a.txt").write_text("precious", encoding="utf-8")
        rc = restore_backup(backup_path=b, dest_dir=dest, dry_run=False,
                            overwrite_policy="keep-both")
        assert rc == 0
        assert (dest / "a.txt").read_text(encoding="utf-8") == "precious"
        siblings = list(dest.glob("a.txt.restored.*"))
        assert len(siblings) == 1
        assert siblings[0].read_text(encoding="utf-8") == "original"

    def test_identical_rerestore_is_idempotent(self, tmp_path):
        b = self._backup(tmp_path, "same")
        dest = tmp_path / "restored"
        rc1 = restore_backup(backup_path=b, dest_dir=dest, dry_run=False,
                             overwrite_policy="fail")
        assert rc1 == 0
        # Second restore: files identical -> not conflicts -> should still succeed with fail policy.
        rc2 = restore_backup(backup_path=b, dest_dir=dest, dry_run=False,
                             overwrite_policy="fail")
        assert rc2 == 0
