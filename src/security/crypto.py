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
KDF_ITERATIONS = 100_000
SALT_BYTES = 16

# Files / dirs (relative to vault root) considered sensitive. Matching is
# case-insensitive for soul.md so Windows (SOUL.md) and Linux (soul.md)
# stay in sync.
SENSITIVE_NAMES = {".env", "config.yaml", "config.yml", "soul.md"}
SENSITIVE_DIRS = {"sessions", "memory", "logs"}


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
        """
        _require_crypto()
        src = Path(input_path)
        raw = src.read_bytes()
        if _is_envelope(raw):
            # Already encrypted — just copy if a different output was asked.
            if output_path and Path(output_path) != src:
                Path(output_path).write_bytes(raw)
                return Path(output_path)
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
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(envelope), encoding="utf-8")
        return dst

    @staticmethod
    def decrypt_file(input_path, password: str, output_path=None) -> Path:
        """Decrypt a JSON-envelope file back to raw bytes."""
        _require_crypto()
        src = Path(input_path)
        raw = src.read_bytes()
        if not _is_envelope(raw):
            if output_path and Path(output_path) != src:
                Path(output_path).write_bytes(raw)
                return Path(output_path)
            return src  # already plaintext
        payload = json.loads(raw.decode("utf-8"))
        plain = EncryptionManager.decrypt_data(payload, password)
        dst = Path(output_path) if output_path else src
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(plain)
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
        if len(rel_parts) > 1 and rel_parts[0].lower() in SENSITIVE_DIRS:
            yield path
        elif len(rel_parts) == 1 and path.name.lower() in SENSITIVE_NAMES:
            yield path


def is_file_encrypted(path: Path) -> bool:
    try:
        return _is_envelope(Path(path).read_bytes())
    except Exception:
        return False


class DataVault:
    """High-level vault rooted at a data directory.

    ``password`` is only needed for lock()/unlock(); status reads work
    without it (which is what health exporters rely on).
    """

    def __init__(self, vault_path, password: str = ""):
        self.root = Path(vault_path)
        self.password = password or ""
        self.config_path = self.root / VAULT_FILENAME

    # -- config ---------------------------------------------------------
    def _read_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"encrypted": False, "files": [], "hardware_token": False}

    def _write_config(self, cfg: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def is_encrypted(self) -> bool:
        return bool(self._read_config().get("encrypted", False))

    # -- operations ------------------------------------------------------
    def lock(self, password: str | None = None, hardware_token: bool = False) -> dict:
        pw = password if password is not None else self.password
        if not pw:
            pw = getpass.getpass("Enter encryption password: ")
            confirm = getpass.getpass("Confirm password: ")
            if pw != confirm:
                raise ValueError("Passwords do not match.")
            if len(pw) < 8:
                raise ValueError("Password must be at least 8 characters.")
        targets = [p for p in _iter_sensitive_files(self.root) if not is_file_encrypted(p)]
        # Also pick up stray plaintext files even when the vault claims locked
        # (e.g. new sessions created while unlocked).
        encrypted_count = 0
        total = 0
        for path in targets:
            EncryptionManager.encrypt_file(path, pw)
            encrypted_count += 1
            try:
                total += path.stat().st_size
            except OSError:
                pass
        # Count pre-existing encrypted files too.
        all_enc = [p for p in _iter_sensitive_files(self.root) if is_file_encrypted(p)]
        self._write_config({
            "encrypted": True,
            "files": sorted(str(p.relative_to(self.root)) for p in all_enc),
            "hardware_token": bool(hardware_token),
        })
        return {"encrypted_files": len(all_enc), "newly_encrypted": encrypted_count,
                "total_size": total}

    def unlock(self, password: str | None = None) -> dict:
        pw = password if password is not None else self.password
        if not pw:
            pw = getpass.getpass("Enter vault password: ")
        if not pw:
            raise ValueError("A password is required to unlock the vault.")
        targets = [p for p in _iter_sensitive_files(self.root) if is_file_encrypted(p)]
        failures: list[str] = []
        count = 0
        for path in targets:
            try:
                EncryptionManager.decrypt_file(path, pw)
                count += 1
            except Exception as exc:  # wrong password → InvalidToken
                failures.append(f"{path}: {exc}")
        if failures:
            raise ValueError(
                "Failed to decrypt %d file(s) — wrong password? (%s)"
                % (len(failures), failures[0])
            )
        cfg = self._read_config()
        cfg["encrypted"] = False
        cfg["files"] = []
        self._write_config(cfg)
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
            "hardware_token_enabled": bool(cfg.get("hardware_token", False)),
        }
        return status


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"
