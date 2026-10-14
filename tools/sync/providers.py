"""providers.py

Storage-provider abstraction for Hermes Agent Pendrive_X sync (P3 — optional features).

Only consider non-AWS providers AFTER S3 sync has reliable verification, per-file
error reporting, and recovery. This module therefore:

- Keeps AWS S3 as the default, verified path (via boto3).
- Adds a generic S3-compatible provider (MinIO, Wasabi, DigitalOcean Spaces,
  Backblaze B2 S3 API, Cloudflare R2, etc.) that reuses the same boto3 code path
  with a custom ``endpoint_url`` — plus explicit verification guidance.
- Adds a local-filesystem provider for offline testing / air-gapped copies.
  It mirrors keys under a root directory and never touches the network.

All providers expose the same minimal interface so conflict handling, dry-run
previews, retention pruning, and verification behave identically.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class StorageProvider:
    """Minimal interface every sync target must implement."""

    name: str = "base"

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, prefix: str = "") -> List[Dict[str, Any]]:
        """Return [{'Key': str, 'Size': int, 'LastModified': str|None}, ...]."""
        raise NotImplementedError

    def upload(self, local_path: Path, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        """Upload local file to key. Returns (ok, message)."""
        raise NotImplementedError

    def delete(self, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        raise NotImplementedError

    def verify(self, local_path: Path, key: str) -> Tuple[bool, str]:
        """Post-upload verification. Returns (ok, message)."""
        return True, "verification skipped"


# ---------------------------------------------------------------------------
# Local filesystem provider (offline, no credentials, fully testable)
# ---------------------------------------------------------------------------

class LocalProvider(StorageProvider):
    name = "local"

    def __init__(self, root_dir: Path | str):
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe = key.replace("\\", "/").strip("/")
        # Guard against traversal.
        parts = [p for p in safe.split("/") if p and p not in (".", "..")]
        return self.root.joinpath(*parts) if parts else self.root

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def list_keys(self, prefix: str = "") -> List[Dict[str, Any]]:
        norm = prefix.replace("\\", "/").strip("/")
        out: List[Dict[str, Any]] = []
        if not self.root.is_dir():
            return out
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(self.root).as_posix()
                if norm and not (rel == norm or rel.startswith(norm.rstrip("/") + "/")):
                    continue
                try:
                    st = p.stat()
                    out.append({"Key": rel, "Size": st.st_size,
                                "LastModified": st.st_mtime})
                except OSError:
                    continue
        return out

    def upload(self, local_path: Path, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        if dry_run:
            return True, f"[DRY-RUN] Would copy {local_path} -> {self.root}/{key}"
        try:
            dest = self._path_for(key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)
            return True, f"Copied {local_path} -> {dest}"
        except Exception as exc:
            return False, f"Local copy failed for {key}: {exc}"

    def delete(self, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        target = self._path_for(key)
        if dry_run:
            return True, f"[DRY-RUN] Would delete {target}"
        try:
            if target.is_file():
                target.unlink()
                return True, f"Deleted {target}"
            return False, f"Not found: {target}"
        except Exception as exc:
            return False, f"Delete failed for {key}: {exc}"

    def verify(self, local_path: Path, key: str) -> Tuple[bool, str]:
        import hashlib

        dest = self._path_for(key)
        if not dest.is_file():
            return False, f"verify: remote copy missing for {key}"
        try:
            lh = hashlib.sha256(local_path.read_bytes()).hexdigest()
            rh = hashlib.sha256(dest.read_bytes()).hexdigest()
            if lh == rh:
                return True, f"verify: SHA-256 match for {key}"
            return False, f"verify: SHA-256 mismatch for {key}"
        except Exception as exc:
            return False, f"verify failed for {key}: {exc}"


# ---------------------------------------------------------------------------
# S3 / S3-compatible provider (boto3)
# ---------------------------------------------------------------------------

class S3Provider(StorageProvider):
    """AWS S3 (default) or any S3-compatible service via endpoint_url."""

    def __init__(self, bucket: str, profile: Optional[str] = None,
                 endpoint_url: Optional[str] = None,
                 region: Optional[str] = None,
                 prefix: str = ""):
        self.bucket = bucket
        self.profile = profile
        self.endpoint_url = endpoint_url
        self.region = region
        self.prefix = prefix
        self.name = "s3-compatible" if endpoint_url else "s3"
        self._client = None

    def client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit(
                "boto3 is required for S3 uploads. Install it with: pip install boto3"
            ) from exc
        try:
            import boto3 as _boto3

            kwargs: Dict[str, Any] = {}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            if self.region:
                kwargs["region_name"] = self.region
            if self.profile:
                session = _boto3.Session(profile_name=self.profile)
                self._client = session.client("s3", **kwargs)
            else:
                self._client = _boto3.client("s3", **kwargs)
            return self._client
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Failed to create S3 client: {exc}", file=__import__("sys").stderr)
            raise SystemExit(2) from exc

    def exists(self, key: str) -> bool:
        try:
            self.client().head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> List[Dict[str, Any]]:
        s3 = self.client()
        full_prefix = "/".join([p for p in (self.prefix, prefix) if p]).strip("/")
        if full_prefix:
            full_prefix += "/"
        out: List[Dict[str, Any]] = []
        token = None
        while True:
            kwargs: Dict[str, Any] = {"Bucket": self.bucket, "Prefix": full_prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                out.append({"Key": obj["Key"], "Size": obj.get("Size", 0),
                            "LastModified": str(obj.get("LastModified", ""))})
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        return out

    def upload(self, local_path: Path, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        if dry_run:
            return True, f"[DRY-RUN] Would upload {local_path} -> s3://{self.bucket}/{key}"
        try:
            self.client().upload_file(str(local_path), self.bucket, key)
            return True, f"Uploaded {local_path} -> s3://{self.bucket}/{key}"
        except Exception as exc:
            return False, f"Upload failed for {local_path} -> s3://{self.bucket}/{key}: {exc}"

    def delete(self, key: str, dry_run: bool = False) -> Tuple[bool, str]:
        if dry_run:
            return True, f"[DRY-RUN] Would delete s3://{self.bucket}/{key}"
        try:
            self.client().delete_object(Bucket=self.bucket, Key=key)
            return True, f"Deleted s3://{self.bucket}/{key}"
        except Exception as exc:
            return False, f"Delete failed for s3://{self.bucket}/{key}: {exc}"

    def verify(self, local_path: Path, key: str) -> Tuple[bool, str]:
        try:
            head = self.client().head_object(Bucket=self.bucket, Key=key)
            remote_size = int(head.get("ContentLength", -1))
            local_size = local_path.stat().st_size
            if remote_size == local_size:
                return True, f"verify: size match ({local_size} bytes) for {key}"
            return False, (
                f"verify: size mismatch for {key} (local {local_size} != remote {remote_size})"
            )
        except Exception as exc:
            return False, f"verify failed for {key}: {exc}"


# ---------------------------------------------------------------------------
# Factory + guidance
# ---------------------------------------------------------------------------

S3_COMPATIBLE_PRESETS: Dict[str, str] = {
    # Preset name -> documentation hint (endpoint still required from user).
    "minio": "Self-hosted MinIO — provide --endpoint-url http://localhost:9000",
    "wasabi": "Wasabi — endpoint like https://s3.wasabisys.com (region-specific)",
    "spaces": "DigitalOcean Spaces — endpoint like https://<region>.digitaloceanspaces.com",
    "b2": "Backblaze B2 S3 API — endpoint like https://s3.<region>.backblazeb2.com",
    "r2": "Cloudflare R2 — endpoint like https://<account>.r2.cloudflarestorage.com",
}

SUPPORTED_PROVIDERS = ("s3", "s3-compatible", "local",
                       "minio", "wasabi", "spaces", "b2", "r2")


def get_provider(name: str, *, bucket: str = "", profile: Optional[str] = None,
                 endpoint_url: Optional[str] = None, region: Optional[str] = None,
                 prefix: str = "", local_dir: Optional[str] = None) -> StorageProvider:
    """Create a storage provider by name.

    Raises SystemExit(2) with actionable guidance for unsupported combos.
    """
    import sys as _sys

    def _fail(msg: str) -> None:
        print(f"[ERROR] {msg}", file=_sys.stderr)
        raise SystemExit(2)

    norm = (name or "s3").lower().strip()
    if norm not in SUPPORTED_PROVIDERS:
        _fail(f"Unknown provider '{name}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}")
    if norm == "local":
        if not local_dir:
            _fail("--provider local requires --local-dir <path>")
        return LocalProvider(local_dir)  # type: ignore[arg-type]
    if norm in S3_COMPATIBLE_PRESETS and not endpoint_url:
        hint = S3_COMPATIBLE_PRESETS[norm]
        _fail(
            f"--provider {norm} requires --endpoint-url. Hint: {hint}. "
            "Only use S3-compatible targets after S3 sync has reliable "
            "verification, error reporting, and recovery (run with --dry-run first)."
        )
    if not bucket:
        _fail(f"--provider {norm} requires --bucket <name>")
    if norm == "s3-compatible" and not endpoint_url:
        _fail("--provider s3-compatible requires --endpoint-url <url>")
    return S3Provider(bucket=bucket, profile=profile,
                      endpoint_url=endpoint_url, region=region, prefix=prefix)


def provider_guidance(name: str) -> str:
    return (
        "Provider notes:\n"
        "- 's3' is the default, verified path (AWS S3 via boto3).\n"
        "- 's3-compatible'/'minio'/'wasabi'/'spaces'/'b2'/'r2' reuse the S3 API with "
        "--endpoint-url. Only adopt these after S3 sync shows reliable verification, "
        "per-file errors, and recovery. Always run --dry-run first.\n"
        "- 'local' mirrors keys under --local-dir for offline/air-gapped testing.\n"
        f"Selected provider: {name}"
    )
