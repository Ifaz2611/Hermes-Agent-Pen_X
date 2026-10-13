"""hardware_token.py — Yubikey / hardware-token support with safe fallbacks."""

from __future__ import annotations

import abc
import shutil


class HardwareTokenManager(abc.ABC):
    """Abstract base for hardware-backed authentication."""

    @abc.abstractmethod
    def is_available(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    @abc.abstractmethod
    def get_info(self) -> dict:  # pragma: no cover
        raise NotImplementedError


class YubikeyManager(HardwareTokenManager):
    """Best-effort Yubikey support via the ``ykman`` CLI / lib."""

    VALID_MODES = ("otp", "fido2", "piv")

    def __init__(self, mode: str = "fido2"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unknown Yubikey mode: {mode!r} (choose from {self.VALID_MODES})")
        self.mode = mode

    def is_available(self) -> bool:
        return shutil.which("ykman") is not None

    def detect(self) -> dict:
        import subprocess

        if not self.is_available():
            return {"connected": False, "reason": "ykman CLI not found"}
        try:
            out = subprocess.run(["ykman", "list"], capture_output=True, text=True, timeout=10)
            connected = bool(out.stdout.strip())
            return {
                "connected": connected,
                "mode": self.mode,
                "device": out.stdout.strip().splitlines()[0] if connected else None,
                "serial": None,
            }
        except Exception as exc:
            return {"connected": False, "reason": str(exc)}

    def get_info(self) -> dict:
        info = self.detect()
        info.setdefault("mode", self.mode)
        return info

    def setup_pin(self) -> dict:
        """Guide the user through FIDO2 PIN setup (delegates to ykman)."""
        import subprocess

        if not self.is_available():
            return {"ok": False, "reason": "ykman CLI not found. Install yubikey-manager."}
        try:
            subprocess.run(["ykman", "fido", "access", "change-pin"], check=False)
            return {"ok": True, "mode": self.mode}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}


class TokenlessAuthManager(HardwareTokenManager):
    """Password-only fallback used when no hardware token is present."""

    def is_available(self) -> bool:
        return True

    def get_info(self) -> dict:
        return {"connected": False, "mode": "password", "fallback": True}


class TokenManager:
    """Unified entry point: prefers Yubikey, falls back to password."""

    def __init__(self, token_type: str = "auto", mode: str = "fido2"):
        self.token_type = token_type
        self.backend: HardwareTokenManager
        if token_type in ("auto", "yubikey"):
            yk = YubikeyManager(mode=mode)
            self.backend = yk if (token_type == "yubikey" or yk.is_available()) else TokenlessAuthManager()
        else:
            self.backend = TokenlessAuthManager()

    def status(self) -> dict:
        try:
            info = self.backend.get_info()
        except Exception as exc:
            info = {"error": str(exc)}
        info["backend"] = type(self.backend).__name__
        return info
