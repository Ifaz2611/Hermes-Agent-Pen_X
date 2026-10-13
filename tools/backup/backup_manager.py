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


def restore_backup(
    backup_path: Path,
    dest_dir: Path,
    dry_run: bool = False
) -> int:
    backup_path = backup_path.resolve()
    dest_dir = dest_dir.resolve()
    
    print(f"\n[RESTORE] Verifying backup integrity before restore...")
    valid, msg, manifest = verify_backup(backup_path)
    if not valid:
        print(f"[ERROR] Restore aborted: {msg}")
        return 1
        
    print(f"[RESTORE] Integrity check passed: {msg}")
    
    enc_count = manifest.get("vault_encrypted_count", 0)
    if enc_count > 0:
        print(f"\n[SECURITY] Restoring {enc_count} vault-encrypted files.")
        print(SECURITY_LIMITATIONS_TEXT)
        
    if dry_run:
        print(f"[DRY-RUN] Would restore {len(manifest.get('files', {}))} files to: {dest_dir}")
        for rel in sorted(manifest.get("files", {}).keys())[:10]:
            print(f"  -> {dest_dir / rel}")
        if len(manifest.get("files", {})) > 10:
            print(f"  ... and {len(manifest.get('files', {})) - 10} more files.")
        return 0
        
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract and perform post-extraction verification
    restored_count = 0
    verification_errors = []
    
    if zipfile.is_zipfile(backup_path):
        with zipfile.ZipFile(backup_path, "r") as zf:
            for rel, info in manifest.get("files", {}).items():
                arc_name = f"data/{rel}"
                target_p = dest_dir / rel
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
            src_p = data_dir / rel
            target_p = dest_dir / rel
            target_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_p, target_p)
            
            h = compute_file_sha256(target_p)
            if h != info["sha256"].lower():
                verification_errors.append(f"{rel}: expected {info['sha256']}, got {h}")
            else:
                restored_count += 1
                
    if verification_errors:
        print(f"[ERROR] Restoration verification failed for {len(verification_errors)} files:")
        for err in verification_errors:
            print(f"  - {err}")
        return 1
        
    print(f"\n[RESTORE] Successfully restored and verified {restored_count} files into: {dest_dir}")
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
    
    # Verify
    p_ver = subparsers.add_parser("verify", help="Verify backup integrity against manifest")
    p_ver.add_argument("backup_file", type=Path, help="Path to backup zip archive or folder")
    
    args = parser.parse_args()
    root = find_repo_root(getattr(args, "root", None))
    
    if args.action == "backup":
        src = args.source if args.source else (root / "data")
        rc, _, _ = create_backup(source_dir=src, dest_path=args.destination, repo_root=root)
        return rc
    elif args.action == "restore":
        dest = args.destination if args.destination else (root / "data")
        return restore_backup(backup_path=args.backup_file, dest_dir=dest, dry_run=args.dry_run)
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
