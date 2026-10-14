"""backup_manager.py

Backup and restore workflow for Hermes Agent Pendrive_X.
Features:
- Configurable source and destination (supports zip archives and directory destinations).
- Preserves full relative directory paths for all user data.
- Generates cryptographic SHA-256 manifests and verifies restored files upon extraction.
- Detects vault-encrypted data and explicitly documents encryption and password recovery limitations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SECURITY_LIMITATIONS_TEXT = """============================================================
      HERMES DATA VAULT - SECURITY & RECOVERY LIMITATIONS
============================================================
1. ENCRYPTION SPECIFICATION:
   Vault-protected files are encrypted using AES-128-CBC (Fernet)
   with keys derived via PBKDF2-HMAC-SHA256 (600,000 iterations)
   from your user-defined passphrase.

2. NO PASSWORD RECOVERY / NO BACKDOOR:
   Hermes does NOT store, escrow, or transmit your password or
   master keys. There is NO password reset, recovery question, or
   backdoor mechanism.

3. CIPHERTEXT PRESERVATION:
   Backups preserve encrypted files in their encrypted ciphertext
   envelope. Restoring this backup to a new computer or USB stick
   will NOT decrypt files or remove encryption requirements.

4. UNRECOVERABLE DATA RISK:
   If you forget or lose your vault passphrase, files protected by
   the vault are mathematically permanent and CANNOT be recovered.
   Always keep a secure, offline record of your vault passphrase.
============================================================
"""


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def find_repo_root(custom_root: Optional[Path] = None) -> Path:
    if custom_root:
        return custom_root.resolve()
    return Path(__file__).resolve().parents[2]


def detect_encrypted_vault_files(source_dir: Path) -> List[str]:
    encrypted = []
    if not source_dir.is_dir():
        return encrypted
    for p in source_dir.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            try:
                head = p.read_bytes()[:128]
                if b'"vault_version"' in head or b'"ciphertext"' in head:
                    encrypted.append(str(p.relative_to(source_dir)))
            except Exception:
                pass
    return encrypted


def create_backup(
    source_dir: Path,
    dest_path: Optional[Path] = None,
    repo_root: Optional[Path] = None
) -> Tuple[int, Path, Dict[str, Any]]:
    root = find_repo_root(repo_root)
    source_dir = source_dir.resolve()
    
    if not source_dir.is_dir():
        print(f"[ERROR] Source directory does not exist: {source_dir}")
        return 1, Path(), {}
        
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if not dest_path:
        backups_dir = root / ".cache" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        dest_path = backups_dir / f"hermes_backup_{now_str}.zip"
    else:
        dest_path = dest_path.resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
    print(f"\n[BACKUP] Starting backup from: {source_dir}")
    print(f"[BACKUP] Destination target:   {dest_path}")
    
    # Check for encrypted files and display notice
    enc_files = detect_encrypted_vault_files(source_dir)
    if enc_files:
        print(f"\n[SECURITY] Detected {len(enc_files)} vault-encrypted files in backup.")
        print(SECURITY_LIMITATIONS_TEXT)
        
    # Gather files and compute checksums
    file_records: Dict[str, Dict[str, Any]] = {}
    total_bytes = 0
    all_files: List[Path] = []
    for p in sorted(source_dir.rglob("*")):
        if p.is_file():
            # Skip transient locks / pids
            if p.name in ("gateway.pid", "health.json"):
                continue
            rel = str(p.relative_to(source_dir)).replace("\\", "/")
            size = p.stat().st_size
            sha = compute_file_sha256(p)
            file_records[rel] = {
                "size": size,
                "sha256": sha
            }
            total_bytes += size
            all_files.append(p)
            
    manifest = {
        "manifest_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dir_name": source_dir.name,
        "total_files": len(file_records),
        "total_bytes": total_bytes,
        "vault_encrypted_count": len(enc_files),
        "vault_encrypted_files": enc_files,
        "security_notice": "Password required for encrypted vault items; no recovery mechanism exists.",
        "files": file_records
    }
    
    # Create archive
    if str(dest_path).endswith(".zip"):
        with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write security notice
            zf.writestr("README_SECURITY.txt", SECURITY_LIMITATIONS_TEXT)
            # Write manifest
            zf.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
            # Write files
            for p in all_files:
                rel = str(p.relative_to(source_dir)).replace("\\", "/")
                zf.write(p, arcname=f"data/{rel}")
    else:
        # Directory destination
        dest_path.mkdir(parents=True, exist_ok=True)
        (dest_path / "README_SECURITY.txt").write_text(SECURITY_LIMITATIONS_TEXT, encoding="utf-8")
        (dest_path / "backup_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        data_dest = dest_path / "data"
        for p in all_files:
            rel = p.relative_to(source_dir)
            target = data_dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            
    print(f"[BACKUP] Successfully created backup with {len(file_records)} files ({total_bytes} bytes).")
    print(f"[BACKUP] Output archive: {dest_path}\n")
    return 0, dest_path, manifest


def verify_backup(backup_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    backup_path = backup_path.resolve()
    if not backup_path.exists():
        return False, f"Backup file not found: {backup_path}", {}
        
    manifest = None
    if zipfile.is_zipfile(backup_path):
        with zipfile.ZipFile(backup_path, "r") as zf:
            if "backup_manifest.json" not in zf.namelist():
                return False, "backup_manifest.json missing from archive", {}
            try:
                manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
            except Exception as e:
                return False, f"Corrupted manifest in archive: {e}", {}
                
            # Verify each file's checksum inside zip
            for rel, info in manifest.get("files", {}).items():
                arc_name = f"data/{rel}"
                if arc_name not in zf.namelist():
                    return False, f"File {arc_name} listed in manifest but missing from zip", manifest
                data = zf.read(arc_name)
                h = hashlib.sha256(data).hexdigest().lower()
                if h != info["sha256"].lower():
                    return False, f"Checksum mismatch for {rel} inside archive (expected {info['sha256']}, got {h})", manifest
    elif backup_path.is_dir():
        m_file = backup_path / "backup_manifest.json"
        if not m_file.is_file():
            return False, "backup_manifest.json missing from backup folder", {}
        try:
            manifest = json.loads(m_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Corrupted manifest: {e}", {}
            
        data_dir = backup_path / "data"
        for rel, info in manifest.get("files", {}).items():
            p = data_dir / rel
            if not p.is_file():
                return False, f"File {rel} missing from backup directory", manifest
            h = compute_file_sha256(p)
            if h != info["sha256"].lower():
                return False, f"Checksum mismatch for {rel} (expected {info['sha256']}, got {h})", manifest
    else:
        return False, f"Unsupported backup format: {backup_path}", {}
        
    return True, f"Verified all {len(manifest.get('files', {}))} files successfully", manifest


def list_backups(backup_dir: Path) -> List[Path]:
    """List backup archives/folders sorted oldest-first (by mtime, then name)."""
    backup_dir = backup_dir.resolve()
    if not backup_dir.is_dir():
        return []
    candidates: List[Path] = []
    for p in backup_dir.iterdir():
        name = p.name
        if p.is_file() and name.startswith("hermes_backup_") and name.endswith(".zip"):
            candidates.append(p)
        elif p.is_dir() and (p / "backup_manifest.json").is_file():
            candidates.append(p)
    def _key(p: Path):
        try:
            return (p.stat().st_mtime, p.name)
        except OSError:
            return (0.0, p.name)
    return sorted(candidates, key=_key)


def prune_backups(
    backup_dir: Path,
    keep_last_n: int,
    dry_run: bool = False,
) -> Tuple[int, str, Dict[str, Any]]:
    """Retention: keep the N newest backups, delete (or preview) older ones.

    Returns (rc, message, details{kept, to_delete}).
    Never deletes the newest N; with keep_last_n<=0 keeps everything.
    """
    backup_dir = backup_dir.resolve()
    if keep_last_n <= 0:
        return 0, "Retention disabled (keep_last_n<=0): keeping all backups.", {
            "kept": [str(p) for p in list_backups(backup_dir)], "to_delete": []}
    if not backup_dir.is_dir():
        return 1, f"Backup directory not found: {backup_dir}", {"kept": [], "to_delete": []}
    all_b = list_backups(backup_dir)
    if len(all_b) <= keep_last_n:
        return 0, (f"Retention: {len(all_b)} backup(s) present, "
                    f"keeping all (keep_last_n={keep_last_n})."), {
            "kept": [str(p) for p in all_b], "to_delete": []}
    to_delete = all_b[:len(all_b) - keep_last_n]
    kept = all_b[len(all_b) - keep_last_n:]
    if dry_run:
        print(f"[DRY-RUN] Retention preview: would keep {len(kept)}, delete {len(to_delete)} "
              f"in {backup_dir} (keep_last_n={keep_last_n}):")
        for p in to_delete:
            print(f"  [DELETE] {p.name}")
        for p in kept:
            print(f"  [KEEP]   {p.name}")
        return 0, (f"Would delete {len(to_delete)} old backup(s), keep {len(kept)}."), {
            "kept": [str(p) for p in kept], "to_delete": [str(p) for p in to_delete]}
    errors = []
    for p in to_delete:
        try:
            if p.is_file():
                p.unlink()
            else:
                shutil.rmtree(p)
            print(f"[PRUNE] Deleted old backup: {p.name}")
        except Exception as exc:
            errors.append(f"{p.name}: {exc}")
    if errors:
        return 1, f"Retention partially failed: {'; '.join(errors)}", {
            "kept": [str(p) for p in kept], "to_delete": [str(p) for p in to_delete]}
    return 0, f"Retention: deleted {len(to_delete)} old backup(s), kept {len(kept)}.", {
        "kept": [str(p) for p in kept], "to_delete": [str(p) for p in to_delete]}


def preview_restore(backup_path: Path, dest_dir: Path) -> Dict[str, Any]:
    """Preview restore actions without modifying files.

    Returns {valid, message, to_create, to_overwrite_same, conflicts, manifest}.
    A conflict = destination exists AND content hash differs from the backup.
    Identical files are safe to skip (not conflicts).
    """
    backup_path = backup_path.resolve()
    dest_dir = dest_dir.resolve()
    valid, msg, manifest = verify_backup(backup_path)
    if not valid:
        return {"valid": False, "message": msg, "to_create": [], "to_overwrite_same": [],
                "conflicts": [], "manifest": {}}
    to_create: List[str] = []
    same: List[str] = []
    conflicts: List[Dict[str, Any]] = []
    for rel, info in manifest.get("files", {}).items():
        target = dest_dir / rel
        if not target.is_file():
            to_create.append(rel)
        else:
            try:
                existing_hash = compute_file_sha256(target)
            except Exception:
                existing_hash = "<unreadable>"
            if existing_hash.lower() == str(info.get("sha256", "")).lower():
                same.append(rel)
            else:
                try:
                    sz = target.stat().st_size
                except OSError:
                    sz = -1
                conflicts.append({"path": rel, "existing_size": sz,
                                  "existing_sha256": existing_hash,
                                  "backup_sha256": info.get("sha256"),
                                  "backup_size": info.get("size")})
    return {"valid": True, "message": msg, "to_create": sorted(to_create),
            "to_overwrite_same": sorted(same), "conflicts": sorted(conflicts, key=lambda c: c["path"]),
            "manifest": manifest}


def restore_backup(
    backup_path: Path,
    dest_dir: Path,
    dry_run: bool = False,
    overwrite_policy: str = "fail",
) -> int:
    """Restore with conflict protection (no silent overwrites).

    overwrite_policy:
      - 'fail': abort if any destination file differs (safest default).
      - 'skip': keep existing differing files, restore only new/identical ones.
      - 'overwrite': overwrite differing files after listing them.
      - 'keep-both': never overwrite; write conflicting restores to
        '<path>.restored.<timestamp>' alongside the existing file.
    Identical files (same SHA-256) are never conflicts and are skipped/verified.
    dry_run always prints a full preview and modifies nothing.
    """
    valid_policies = ("fail", "skip", "overwrite", "keep-both")
    if overwrite_policy not in valid_policies:
        print(f"[ERROR] Unknown --overwrite-policy '{overwrite_policy}'. "
              f"Choose from: {', '.join(valid_policies)}")
        return 2
    backup_path = backup_path.resolve()
    dest_dir = dest_dir.resolve()

    print("\n[RESTORE] Verifying backup integrity before restore...")
    preview = preview_restore(backup_path, dest_dir)
    if not preview["valid"]:
        print(f"[ERROR] Restore aborted: {preview['message']}")
        return 1
    manifest = preview["manifest"]

    print(f"[RESTORE] Integrity check passed: {preview['message']}")

    enc_count = manifest.get("vault_encrypted_count", 0)
    if enc_count > 0:
        print(f"\n[SECURITY] Restoring {enc_count} vault-encrypted files.")
        print(SECURITY_LIMITATIONS_TEXT)

    to_create = preview["to_create"]
    same = preview["to_overwrite_same"]
    conflicts = preview["conflicts"]
    print(f"[RESTORE] Preview: {len(to_create)} new, {len(same)} identical (skip), "
          f"{len(conflicts)} conflict(s, exist + differ) -> {dest_dir}")
    for rel in sorted(to_create)[:10]:
        print(f"  [CREATE] {rel}")
    if len(to_create) > 10:
        print(f"  ... and {len(to_create) - 10} more new files.")
    for c in conflicts[:10]:
        print(f"  [CONFLICT] {c['path']} (existing {c['existing_size']}b "
              f"{c['existing_sha256'][:12] if len(str(c['existing_sha256'])) > 12 else c['existing_sha256']} "
              f"!= backup {str(c['backup_sha256'])[:12]})")
    if len(conflicts) > 10:
        print(f"  ... and {len(conflicts) - 10} more conflicts.")
    print(f"[RESTORE] Overwrite policy: {overwrite_policy}")

    if dry_run:
        print("[DRY-RUN] Preview only — no files were modified.")
        if conflicts and overwrite_policy == "fail":
            print("[DRY-RUN] With --overwrite-policy fail this restore WOULD abort.")
        return 0

    if conflicts and overwrite_policy == "fail":
        print(f"[ERROR] Restore aborted: {len(conflicts)} existing file(s) would be "
              "overwritten. Nothing was modified.")
        print("  Resolve with --overwrite-policy skip|overwrite|keep-both, or back up "
              "the destination first. Preview with --dry-run.")
        return 1

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Determine skip set for 'skip' policy.
    skip_paths = {c["path"] for c in conflicts} if overwrite_policy == "skip" else set()
    if skip_paths:
        print(f"[RESTORE] Skipping {len(skip_paths)} conflicting file(s) (policy=skip).")

    ts_suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def _target_for(rel: str) -> Path:
        if overwrite_policy == "keep-both" and any(c["path"] == rel for c in conflicts):
            base = dest_dir / rel
            return base.with_name(base.name + f".restored.{ts_suffix}")
        return dest_dir / rel

    # Extract and perform post-extraction verification
    restored_count = 0
    skipped_count = 0
    kept_both: List[str] = []
    verification_errors = []

    if zipfile.is_zipfile(backup_path):
        with zipfile.ZipFile(backup_path, "r") as zf:
            for rel, info in manifest.get("files", {}).items():
                if rel in skip_paths:
                    skipped_count += 1
                    continue
                arc_name = f"data/{rel}"
                target_p = _target_for(rel)
                if str(target_p) != str(dest_dir / rel):
                    kept_both.append(f"{rel} -> {target_p.name}")
                target_p.parent.mkdir(parents=True, exist_ok=True)

                content = zf.read(arc_name)
                target_p.write_bytes(content)

                # Immediate post-extraction verification
                h = compute_file_sha256(target_p)
                if h != info["sha256"].lower():
                    verification_errors.append(f"{rel}: expected {info['sha256']}, got {h}")
                else:
                    restored_count += 1
    elif backup_path.is_dir():
        data_dir = backup_path / "data"
        for rel, info in manifest.get("files", {}).items():
            if rel in skip_paths:
                skipped_count += 1
                continue
            src_p = data_dir / rel
            target_p = _target_for(rel)
            if str(target_p) != str(dest_dir / rel):
                kept_both.append(f"{rel} -> {target_p.name}")
            target_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_p, target_p)

            h = compute_file_sha256(target_p)
            if h != info["sha256"].lower():
                verification_errors.append(f"{rel}: expected {info['sha256']}, got {h}")
            else:
                restored_count += 1
    else:
        print(f"[ERROR] Unsupported backup format: {backup_path}")
        return 1

    if verification_errors:
        print(f"[ERROR] Restoration verification failed for {len(verification_errors)} files:")
        for err in verification_errors:
            print(f"  - {err}")
        return 1

    print(f"\n[RESTORE] Successfully restored and verified {restored_count} files into: {dest_dir}")
    if skipped_count:
        print(f"[RESTORE] Skipped {skipped_count} conflicting file(s) (existing data preserved).")
    if kept_both:
        print(f"[RESTORE] keep-both: {len(kept_both)} file(s) written alongside existing data:")
        for entry in kept_both[:10]:
            print(f"  - {entry}")
    print("[RESTORE] Complete.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup and restore Hermes user data with cryptographic verification.")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")
    
    # Backup
    p_bak = subparsers.add_parser("backup", help="Create a verified backup of user data")
    p_bak.add_argument("--source", type=Path, default=None, help="Source data directory (default: data/)")
    p_bak.add_argument("--destination", "--dest", type=Path, default=None, help="Destination archive (.zip) or folder")
    p_bak.add_argument("--root", type=Path, default=None, help="Repository root path")
    
    # Restore
    p_res = subparsers.add_parser("restore", help="Restore and verify user data from backup")
    p_res.add_argument("backup_file", type=Path, help="Path to backup zip archive or folder")
    p_res.add_argument("--destination", "--dest", type=Path, default=None, help="Restore destination directory (default: data/)")
    p_res.add_argument("--root", type=Path, default=None, help="Repository root path")
    p_res.add_argument("--dry-run", action="store_true", help="Preview restore without modifying files")
    p_res.add_argument("--overwrite-policy", choices=("fail", "skip", "overwrite", "keep-both"),
                       default="fail",
                       help="How to handle existing differing files (default: fail = abort, no silent overwrites)")
    p_res.add_argument("--overwrite", action="store_true",
                       help="Shorthand for --overwrite-policy overwrite (explicit opt-in to replace existing files)")

    # Verify
    p_ver = subparsers.add_parser("verify", help="Verify backup integrity against manifest")
    p_ver.add_argument("backup_file", type=Path, help="Path to backup zip archive or folder")

    # Prune (retention)
    p_pru = subparsers.add_parser("prune", help="Apply retention: keep N newest backups, preview/delete older ones")
    p_pru.add_argument("--backup-dir", type=Path, default=None,
                       help="Directory containing backups (default: .cache/backups/)")
    p_pru.add_argument("--keep", type=int, default=5, help="Keep last N backups (default 5)")
    p_pru.add_argument("--root", type=Path, default=None, help="Repository root path")
    p_pru.add_argument("--dry-run", action="store_true", help="Preview without deleting")

    args = parser.parse_args()
    root = find_repo_root(getattr(args, "root", None))

    if args.action == "backup":
        src = args.source if args.source else (root / "data")
        rc, _, _ = create_backup(source_dir=src, dest_path=args.destination, repo_root=root)
        return rc
    elif args.action == "restore":
        dest = args.destination if args.destination else (root / "data")
        policy = "overwrite" if getattr(args, "overwrite", False) else args.overwrite_policy
        return restore_backup(backup_path=args.backup_file, dest_dir=dest,
                              dry_run=args.dry_run, overwrite_policy=policy)
    elif args.action == "prune":
        bdir = args.backup_dir if args.backup_dir else (root / ".cache" / "backups")
        rc, msg, _ = prune_backups(backup_dir=bdir, keep_last_n=args.keep, dry_run=args.dry_run)
        print(f"[PRUNE] {msg}")
        return rc
    elif args.action == "verify":
        ok, msg, _ = verify_backup(args.backup_file)
        if ok:
            print(f"[PASS] {msg}")
            return 0
        else:
            print(f"[FAIL] {msg}")
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
