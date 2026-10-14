"""Tests for P3 scheduled backup/sync (opt-in, explain uploads, pause/disable)."""

from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))

from tools.sync.schedule_manager import (
    load_schedule,
    save_schedule,
    is_due,
    mark_ran,
    cmd_status,
    cmd_enable,
    cmd_disable,
    cmd_pause,
    cmd_resume,
    cmd_run,
    describe_source,
    build_parser,
)


def _enable_args(mode="backup", **kw):
    import argparse
    ns = argparse.Namespace(
        interval_hours=kw.get("interval_hours", 24.0),
        mode=mode,
        data_dir=kw.get("data_dir", None),
        destination=kw.get("destination", None),
        retention_keep=kw.get("retention_keep", 0),
        bucket=kw.get("bucket", None),
        prefix=kw.get("prefix", ""),
        provider=kw.get("provider", "s3"),
        endpoint_url=kw.get("endpoint_url", None),
        region=kw.get("region", None),
        encrypt=kw.get("encrypt", False),
        no_overwrite=kw.get("no_overwrite", False),
    )
    return ns


class TestScheduleOptIn:
    def test_disabled_by_default(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".cache").mkdir()
        assert load_schedule(root) is None
        rc = cmd_status(root)
        assert rc == 0
        out = capsys.readouterr().out
        assert "DISABLED (opt-in)" in out
        assert "Nothing is uploaded automatically" in out

    def test_enable_backup_explains_uploads(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        data = root / "data"
        data.mkdir()
        (data / "a.txt").write_text("hello", encoding="utf-8")
        rc = cmd_enable(root, _enable_args(mode="backup"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Schedule enabled (opt-in)" in out
        assert "What data is uploaded" in out
        assert "a.txt" in out or "1 file(s)" in out
        sched = load_schedule(root)
        assert sched["enabled"] is True
        assert sched["paused"] is False
        assert sched["mode"] == "backup"

    def test_enable_s3_requires_bucket(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        rc = cmd_enable(root, _enable_args(mode="s3", bucket=None))
        assert rc == 2

    def test_pause_resume_disable(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        cmd_enable(root, _enable_args(mode="backup"))
        capsys.readouterr()
        assert cmd_pause(root) == 0
        sched = load_schedule(root)
        assert sched["paused"] is True
        due, reason = is_due(sched)
        assert due is False and "paused" in reason
        assert cmd_resume(root) == 0
        assert load_schedule(root)["paused"] is False
        assert cmd_disable(root) == 0
        assert load_schedule(root)["enabled"] is False
        due2, _ = is_due(load_schedule(root))
        assert due2 is False

    def test_run_now_dry_run_does_not_advance(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        data = root / "data"
        data.mkdir()
        (data / "f.txt").write_text("x", encoding="utf-8")
        cmd_enable(root, _enable_args(mode="backup"))
        capsys.readouterr()
        before = load_schedule(root).get("last_run")
        rc = cmd_run(root, dry_run=True, force=True)
        assert rc == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert load_schedule(root).get("last_run") == before

    def test_run_now_real_backup_and_marks_ran(self, tmp_path, capsys):
        root = tmp_path / "repo"
        root.mkdir()
        data = root / "data"
        data.mkdir()
        (data / "f.txt").write_text("real", encoding="utf-8")
        dest = tmp_path / "out.zip"
        cmd_enable(root, _enable_args(mode="backup", destination=str(dest)))
        capsys.readouterr()
        rc = cmd_run(root, dry_run=False, force=True)
        assert rc == 0
        assert dest.is_file()
        sched = load_schedule(root)
        assert sched.get("last_run")
        assert sched.get("next_run")

    def test_describe_source_counts_encrypted(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "plain.txt").write_text("hi", encoding="utf-8")
        (data / "enc.json").write_text('{"vault_version": 1, "ciphertext": "xx"}', encoding="utf-8")
        info = describe_source(data)
        assert info["file_count"] == 2
        assert info["encrypted_files"] == 1
