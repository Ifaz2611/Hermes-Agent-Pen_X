"""crypto.py — AES-256 (Fernet) encryption + portable DataVault.

File envelope format (JSON, UTF-8) written in place of the plaintext file:

    {"__hermes_vault__": 1, "version": 1, "salt": "<b64>", "token": "<fernet>",
     "original_name": "<filename>"}

Key derivation: PBKDF2-HMAC-SHA256, 100_000 iterations, 16-byte random salt.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
from pathlib import Path
import shutil

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:  # pragma: no cover - surfaced clearly to callers
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    PBKDF2HMAC = None  # type: ignore
    hashes = None  # type: ignore


VAULT_MARKER = "__hermes_vault__"
VAULT_FILENAME = ".vault"
VAULT_BACKUP_DIR = ".vault_backup"
KDF_ITERATIONS = 100_000
SALT_BYTES = 16

# Files / dirs (relative to vault root) considered sensitive. Matching is
# case-insensitive for soul.md so Windows (SOUL.md) and Linux (soul.md)
# stay in sync.
SENSITIVE_NAMES = {".env", "config.yaml", "config.yml", "soul.md"}
SENSITIVE_DIRS = {"sessions", "memory", "logs"}


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write data to target path atomically via a temporary file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.parent / f".tmp_{target.name}_{os.getpid()}_{os.urandom(4).hex()}"
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def _atomic_write_text(target: Path, text: str, encoding: str = "utf-8") -> None:
    """Write string to target path atomically."""
    _atomic_write_bytes(target, text.encode(encoding))


def _require_crypto() -> None:
    if Fernet is None or PBKDF2HMAC is None:
        raise RuntimeError(
            "The 'cryptography' package is required for vault operations. "
            "Install it with: pip install 'cryptography>=41.0.0'"
        )


def _derive_key(password: str, salt: bytes) -> bytes:
    _require_crypto()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _is_envelope(data: bytes) -> bool:
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        return False
    return isinstance(obj, dict) and obj.get(VAULT_MARKER) == 1


class EncryptionManager:
    """Stateless Fernet helpers + file envelope helpers.

    All methods are static so both call styles work::

        EncryptionManager.encrypt_file(path, password, output_path=...)
        EncryptionManager().encrypt_file(path, password)
    """

    def __init__(self, password: str | None = None):
        self.password = password

    def _pw(self, password: str | None) -> str:
        pw = password if password is not None else self.password
        if not pw:
            raise ValueError("An encryption password is required.")
        return pw

    # -- raw data ------------------------------------------------------
    @staticmethod
    def encrypt_data(data: bytes, password: str) -> dict:
        _require_crypto()
        if not password:
            raise ValueError("An encryption password is required.")
        salt = os.urandom(SALT_BYTES)
        token = Fernet(_derive_key(password, salt)).encrypt(data)
        return {
            "salt": base64.b64encode(salt).decode("ascii"),
            "token": token.decode("ascii"),
        }

    @staticmethod
    def decrypt_data(payload: dict, password: str) -> bytes:
        _require_crypto()
        if not password:
            raise ValueError("A decryption password is required.")
        salt = base64.b64decode(payload["salt"])
        token = payload["token"].encode("ascii")
        return Fernet(_derive_key(password, salt)).decrypt(token)

    # -- files ----------------------------------------------------------
    @staticmethod
    def encrypt_file(input_path, password: str, output_path=None) -> Path:
        """Encrypt a file into the JSON envelope.

        Returns the path written. Defaults to in-place (same path).
        Writes file contents atomically.
        """
        _require_crypto()
        src = Path(input_path)
        raw = src.read_bytes()
        if _is_envelope(raw):
            # Already encrypted — just copy atomically if a different output was asked.
            if output_path and Path(output_path) != src:
                dst = Path(output_path)
                _atomic_write_bytes(dst, raw)
                return dst
            return src
        bundle = EncryptionManager.encrypt_data(raw, password)
        envelope = {
            VAULT_MARKER: 1,
            "version": 1,
            "salt": bundle["salt"],
            "token": bundle["token"],
            "original_name": src.name,
        }
        dst = Path(output_path) if output_path else src
        _atomic_write_text(dst, json.dumps(envelope), encoding="utf-8")
        return dst

    @staticmethod
    def decrypt_file(input_path, password: str, output_path=None) -> Path:
        """Decrypt a JSON-envelope file back to raw bytes.

        Writes file contents atomically.
        """
        _require_crypto()
        src = Path(input_path)
        raw = src.read_bytes()
        if not _is_envelope(raw):
            if output_path and Path(output_path) != src:
                dst = Path(output_path)
                _atomic_write_bytes(dst, raw)
                return dst
            return src  # already plaintext
        payload = json.loads(raw.decode("utf-8"))
        plain = EncryptionManager.decrypt_data(payload, password)
        dst = Path(output_path) if output_path else src
        _atomic_write_bytes(dst, plain)
        return dst

    # -- instance conveniences ------------------------------------------
    def encrypt(self, data: bytes, password: str | None = None) -> dict:
        return self.encrypt_data(data, self._pw(password))

    def decrypt(self, payload: dict, password: str | None = None) -> bytes:
        return self.decrypt_data(payload, self._pw(password))


def _iter_sensitive_files(root: Path):
    """Yield sensitive files under root (case-insensitive name match)."""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == VAULT_FILENAME or path.suffix == ".enc":
            continue
        rel_parts = path.relative_to(root).parts
        if any(p == VAULT_BACKUP_DIR or p.startswith(".tmp_") or p.endswith(".bak") for p in rel_parts):
            continue
        if len(rel_parts) > 1 and rel_parts[0].lower() in SENSITIVE_DIRS:
            yield path
        elif len(rel_parts) == 1 and path.name.lower() in SENSITIVE_NAMES:
            yield path


def is_file_encrypted(path: Path) -> bool:
    try:
        return _is_envelope(Path(path).read_bytes())
    except Exception:
        return False


class VaultBackupManager:
    """Manages transactional backups of vault files during updates."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.backup_dir = self.root / VAULT_BACKUP_DIR
        self.manifest_file = self.backup_dir / "operation.json"

    def has_pending_backup(self) -> bool:
        return self.manifest_file.is_file()

    def read_manifest(self) -> dict | None:
        if not self.has_pending_backup():
            return None
        try:
            return json.loads(self.manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def create_backup(self, operation: str, target_files: list[Path], current_config: dict) -> None:
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        relative_files = []
        files_backup_dir = self.backup_dir / "files"
        for path in target_files:
            rel = path.relative_to(self.root)
            relative_files.append(str(rel))
            dest = files_backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(dest, path.read_bytes())

        manifest = {
            "operation": operation,
            "files": relative_files,
            "config": current_config,
        }
        _atomic_write_text(self.manifest_file, json.dumps(manifest, indent=2))

    def restore(self) -> list[str]:
        """Restore all backed-up files and config, leaving vault in pre-operation state."""
        if not self.has_pending_backup():
            return []
        manifest = self.read_manifest()
        if not manifest:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir, ignore_errors=True)
            return []

        restored: list[str] = []
        files_backup_dir = self.backup_dir / "files"
        for rel_str in manifest.get("files", []):
            src_bak = files_backup_dir / rel_str
            dst_real = self.root / rel_str
            if src_bak.exists():
                dst_real.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_bytes(dst_real, src_bak.read_bytes())
                restored.append(rel_str)

        config = manifest.get("config")
        config_path = self.root / VAULT_FILENAME
        if config is not None:
            _atomic_write_text(config_path, json.dumps(config, indent=2))

        # Clear the backup after successful restore
        shutil.rmtree(self.backup_dir, ignore_errors=True)
        return restored

    def commit(self) -> None:
        """Operation finished successfully; remove backup."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)


class DataVault:
    """High-level vault rooted at a data directory.

    ``password`` is only needed for lock()/unlock(); status reads work
    without it (which is what health exporters rely on).
    """

    def __init__(self, vault_path, password: str = ""):
        self.root = Path(vault_path)
        self.password = password or ""
        self.config_path = self.root / VAULT_FILENAME
        self._backup_mgr = VaultBackupManager(self.root)

    # -- config ---------------------------------------------------------
    def _read_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"encrypted": False, "files": []}

    def _write_config(self, cfg: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(self.config_path, json.dumps(cfg, indent=2))

    def is_encrypted(self) -> bool:
        return bool(self._read_config().get("encrypted", False))

    def has_pending_recovery(self) -> bool:
        """Check if an interrupted operation left recoverable backups."""
        return self._backup_mgr.has_pending_backup()

    def recover(self) -> dict:
        """Recover from an interrupted lock or unlock operation using preserved backups."""
        if not self.has_pending_recovery():
            return {"recovered": False, "recovered_files": 0, "files": []}
        restored = self._backup_mgr.restore()
        return {"recovered": True, "recovered_files": len(restored), "files": restored}

    # -- operations ------------------------------------------------------
    def lock(self, password: str | None = None, hardware_token: bool = False) -> dict:
        if self.has_pending_recovery():
            self.recover()

        pw = password if password is not None else self.password
        if not pw:
            pw = getpass.getpass("Enter encryption password: ")
            confirm = getpass.getpass("Confirm password: ")
            if pw != confirm:
                raise ValueError("Passwords do not match.")
            if len(pw) < 8:
                raise ValueError("Password must be at least 8 characters.")

        targets = [p for p in _iter_sensitive_files(self.root) if not is_file_encrypted(p)]
        cfg = self._read_config()

        # Preserve recoverable backups before modifying any files
        self._backup_mgr.create_backup("lock", targets, cfg)

        encrypted_count = 0
        total = 0
        try:
            for path in targets:
                EncryptionManager.encrypt_file(path, pw)
                encrypted_count += 1
                try:
                    total += path.stat().st_size
                except OSError:
                    pass

            all_enc = [p for p in _iter_sensitive_files(self.root) if is_file_encrypted(p)]
            self._write_config({
                "encrypted": True,
                "files": sorted(str(p.relative_to(self.root)) for p in all_enc),
            })
            self._backup_mgr.commit()
        except Exception:
            self._backup_mgr.restore()
            raise

        return {
            "encrypted_files": len(all_enc),
            "newly_encrypted": encrypted_count,
            "total_size": total,
        }

    def unlock(self, password: str | None = None) -> dict:
        if self.has_pending_recovery():
            self.recover()

        pw = password if password is not None else self.password
        if not pw:
            pw = getpass.getpass("Enter vault password: ")
        if not pw:
            raise ValueError("A password is required to unlock the vault.")

        targets = [p for p in _iter_sensitive_files(self.root) if is_file_encrypted(p)]
        cfg = self._read_config()

        # Preserve recoverable backups before modifying any files
        self._backup_mgr.create_backup("unlock", targets, cfg)

        count = 0
        failures: list[str] = []
        try:
            for path in targets:
                try:
                    EncryptionManager.decrypt_file(path, pw)
                    count += 1
                except Exception as exc:  # wrong password → InvalidToken
                    failures.append(f"{path}: {exc}")
                    break

            if failures:
                raise ValueError(
                    "Failed to decrypt %d file(s) — wrong password? (%s)"
                    % (len(failures), failures[0])
                )

            new_cfg = self._read_config()
            new_cfg["encrypted"] = False
            new_cfg["files"] = []
            self._write_config(new_cfg)
            self._backup_mgr.commit()
        except Exception:
            self._backup_mgr.restore()
            raise

        return {"decrypted_files": count}

    def get_vault_status(self) -> dict:
        cfg = self._read_config()
        files = list(_iter_sensitive_files(self.root))
        enc = [p for p in files if is_file_encrypted(p)]
        size = 0
        for p in files:
            try:
                size += p.stat().st_size
            except OSError:
                pass
        status = {
            "vault_path": str(self.root),
            "encrypted": bool(cfg.get("encrypted", False)) or len(enc) > 0,
            "encrypted_files": len(enc),
            "total_files": len(files),
            "total_size": size,
            # aliases for older consumers (dashboard.js,cli)
            "vault_size": size,
            "total_size_human": _human(size),
            "pending_recovery": self.has_pending_recovery(),
        }
        return status


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"
