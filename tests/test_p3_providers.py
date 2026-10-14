"""Tests for P3 storage providers + S3 conflict/retention handling."""

from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "tools" / "sync"))
sys.path.insert(0, str(repo_root / "src"))

from providers import LocalProvider, get_provider
from s3_sync import main as s3_main


class TestProviders:
    def test_local_upload_list_verify_delete(self, tmp_path):
        root = tmp_path / "remote"
        prov = LocalProvider(root)
        src = tmp_path / "a.txt"
        src.write_text("hello", encoding="utf-8")
        ok, _ = prov.upload(src, "prefix/a.txt", dry_run=True)
        assert ok and not (root / "prefix" / "a.txt").exists()
        ok, _ = prov.upload(src, "prefix/a.txt", dry_run=False)
        assert ok and (root / "prefix" / "a.txt").exists()
        assert prov.exists("prefix/a.txt")
        keys = prov.list_keys("prefix")
        assert any(o["Key"] == "prefix/a.txt" for o in keys)
        vok, _ = prov.verify(src, "prefix/a.txt")
        assert vok
        ok, _ = prov.delete("prefix/a.txt", dry_run=False)
        assert ok and not prov.exists("prefix/a.txt")

    def test_local_traversal_safe(self, tmp_path):
        prov = LocalProvider(tmp_path / "r")
        src = tmp_path / "x.txt"
        src.write_text("x", encoding="utf-8")
        ok, _ = prov.upload(src, "../evil.txt", dry_run=False)
        assert ok
        assert not (tmp_path / "evil.txt").exists()

    def test_factory_local_requires_dir(self, tmp_path):
        try:
            get_provider("local")
            assert False, "should have raised"
        except SystemExit as e:
            assert e.code == 2

    def test_factory_s3_compatible_requires_endpoint(self):
        for name in ("s3-compatible", "minio", "wasabi"):
            try:
                get_provider(name, bucket="b")
                assert False, f"{name} should require endpoint"
            except SystemExit as e:
                assert e.code == 2

    def test_factory_unknown(self):
        try:
            get_provider("dropbox", bucket="b")
            assert False
        except SystemExit:
            pass


def _data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    (d / "f1.txt").write_text("one", encoding="utf-8")
    (d / "f2.txt").write_text("two", encoding="utf-8")
    return d


class TestS3Conflicts:
    def test_local_provider_sync(self, tmp_path, capsys):
        data = _data(tmp_path)
        remote = tmp_path / "remote"
        rc = s3_main(["--bucket", "ignored", "--data-dir", str(data),
                      "--provider", "local", "--local-dir", str(remote)])
        assert rc == 0
        assert (remote / "f1.txt").exists()

    def test_local_no_overwrite_skip(self, tmp_path, capsys):
        data = _data(tmp_path)
        remote = tmp_path / "remote"
        remote.mkdir()
        (remote / "f1.txt").write_text("REMOTE precious", encoding="utf-8")
        rc = s3_main(["--bucket", "ignored", "--data-dir", str(data),
                      "--provider", "local", "--local-dir", str(remote),
                      "--no-overwrite"])
        assert rc == 0
        # Remote preserved.
        assert (remote / "f1.txt").read_text(encoding="utf-8") == "REMOTE precious"
        # New file still synced.
        assert (remote / "f2.txt").exists()

    def test_conflict_fail_aborts(self, tmp_path, capsys):
        data = _data(tmp_path)
        remote = tmp_path / "remote"
        remote.mkdir()
        (remote / "f1.txt").write_text("REMOTE", encoding="utf-8")

        class FakeS3:
            def list_objects_v2(self, Bucket, Prefix=""):
                return {"Contents": [{"Key": "f1.txt"}, {"Key": "f2.txt"}], "IsTruncated": False}

            def upload_file(self, a, b, c):
                return None

        import s3_sync
        orig = s3_sync.s3_client
        s3_sync.s3_client = lambda profile=None, endpoint_url=None, region=None: FakeS3()
        try:
            rc = s3_main(["--bucket", "b", "--data-dir", str(data),
                          "--conflict-policy", "fail"])
            assert rc == 1
        finally:
            s3_sync.s3_client = orig

    def test_dry_run_previews_without_creds(self, tmp_path, capsys):
        data = _data(tmp_path)
        rc = s3_main(["--bucket", "b", "--data-dir", str(data),
                      "--dry-run", "--conflict-policy", "fail",
                      "--retention-keep", "2"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[DRY-RUN] Would upload" in out
        assert "Retention preview" in out
