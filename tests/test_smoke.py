"""Cross-platform smoke tests.

Exercises:
1. Launcher argument forwarding (--help, --version, /profile, subcommands).
2. Setup dry runs (PowerShell setup-windows.ps1, Unix setup-unix.sh).
3. Vault unlocking (unlock-vault.ps1, unlock-vault.sh).
4. Reset previews (reset-windows.ps1, reset-unix.sh).
"""

import os
import sys
import shutil
import subprocess
import tempfile
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")

def get_bash_executable():
    if sys.platform == "win32":
        for git_bash in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Git\bin\bash.exe",
        ]:
            if os.path.exists(git_bash):
                return git_bash
    which_bash = shutil.which("bash")
    if which_bash and "System32" not in which_bash:
        return which_bash
    if which_bash:
        try:
            res = subprocess.run([which_bash, "-c", "echo ok"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                return which_bash
        except Exception:
            pass
    return None

BASH_EXE = get_bash_executable()
HAS_BASH = BASH_EXE is not None
IS_WINDOWS = sys.platform == "win32"


class TestLauncherHelpAndVersion:
    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows batch tests require Windows")
    def test_windows_launch_bat_help(self):
        bat_path = os.path.join(REPO_ROOT, "launch.bat")
        for flag in ["--help", "-h", "/?"]:
            res = subprocess.run(
                ["cmd", "/c", bat_path, flag],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Failed for flag {flag}: {res.stderr}"
            assert "Hermes Pendrive_X" in res.stdout
            assert "Usage:" in res.stdout
            assert "Options:" in res.stdout

    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows batch tests require Windows")
    def test_windows_launch_bat_version(self):
        bat_path = os.path.join(REPO_ROOT, "launch.bat")
        for flag in ["--version", "-v"]:
            res = subprocess.run(
                ["cmd", "/c", bat_path, flag],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Failed for flag {flag}: {res.stderr}"
            assert "Launcher version:" in res.stdout

    @pytest.mark.skipif(not HAS_BASH, reason="Bash executable required for Unix launcher tests")
    def test_unix_launch_sh_help(self):
        sh_path = os.path.join(REPO_ROOT, "launch.sh")
        for flag in ["--help", "-h"]:
            res = subprocess.run(
                [BASH_EXE, sh_path, flag],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Failed for flag {flag}: {res.stderr}"
            assert "Hermes Pendrive_X" in res.stdout
            assert "Usage:" in res.stdout

    @pytest.mark.skipif(not HAS_BASH, reason="Bash executable required for Unix launcher tests")
    def test_unix_launch_sh_version(self):
        sh_path = os.path.join(REPO_ROOT, "launch.sh")
        for flag in ["--version", "-v"]:
            res = subprocess.run(
                [BASH_EXE, sh_path, flag],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Failed for flag {flag}: {res.stderr}"
            assert "Launcher version:" in res.stdout


class TestLauncherArgumentForwarding:
    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows batch tests require Windows")
    def test_windows_launch_bat_profile_forwarding(self, tmp_path):
        """Test that launch.bat profile list forwards to profile_manager.py properly."""
        # Create a mock environment with ready.flag so launch.bat doesn't enter setup
        runtime_dir = os.path.join(REPO_ROOT, ".cache", "runtimes", "windows-x64")
        flag_file = os.path.join(runtime_dir, "ready.flag")
        flag_created = False
        if not os.path.exists(flag_file):
            os.makedirs(runtime_dir, exist_ok=True)
            with open(flag_file, "w") as f:
                f.write("ready")
            flag_created = True

        try:
            bat_path = os.path.join(REPO_ROOT, "launch.bat")
            env = os.environ.copy()
            env["PYTHONPATH"] = SRC_DIR
            res = subprocess.run(
                ["cmd", "/c", bat_path, "profile", "list"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=env,
            )
            # Exit code 0 and lists profiles
            assert res.returncode == 0
            assert "Available profiles" in res.stdout or "No profiles found" in res.stdout
        finally:
            if flag_created and os.path.exists(flag_file):
                try:
                    os.remove(flag_file)
                except OSError:
                    pass

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    def test_unix_launch_sh_profile_forwarding(self):
        """Test that launch.sh profile list forwards to profile_manager.py properly."""
        sh_path = os.path.join(REPO_ROOT, "launch.sh")
        env = os.environ.copy()
        env["HERMES_PLATFORM"] = "linux"
        env["HERMES_ARCH"] = "x64"
        env["PYTHONPATH"] = SRC_DIR

        # Create temporary ready flag in cache
        cache_runtime = os.path.join(REPO_ROOT, ".cache", "runtimes", "linux-x64")
        flag_file = os.path.join(cache_runtime, "ready.flag")
        flag_created = False
        if not os.path.exists(flag_file):
            os.makedirs(cache_runtime, exist_ok=True)
            with open(flag_file, "w") as f:
                f.write("ready")
            flag_created = True

        try:
            res = subprocess.run(
                [BASH_EXE, sh_path, "profile", "list"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env=env,
            )
            assert res.returncode == 0
            assert "Available profiles" in res.stdout or "No profiles found" in res.stdout
        finally:
            if flag_created and os.path.exists(flag_file):
                try:
                    os.remove(flag_file)
                except OSError:
                    pass

    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows batch tests require Windows")
    def test_windows_launch_bat_diagnostics_forwarding(self):
        bat_path = os.path.join(REPO_ROOT, "launch.bat")
        res = subprocess.run(
            ["cmd", "/c", bat_path, "diagnostics"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        assert "Portable Wrapper Diagnostics" in res.stdout
        assert "Host Platform:" in res.stdout

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    def test_unix_launch_sh_diagnostics_forwarding(self):
        sh_path = os.path.join(REPO_ROOT, "launch.sh")
        env = os.environ.copy()
        env["HERMES_PLATFORM"] = "linux"
        env["HERMES_ARCH"] = "x64"
        env["PYTHONPATH"] = SRC_DIR
        res = subprocess.run(
            [BASH_EXE, sh_path, "diagnostics"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0, f"Diagnostics failed: {res.stderr}"
        assert "Portable Wrapper Diagnostics" in res.stdout

    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows batch tests require Windows")
    def test_windows_launch_bat_upgrade_preview_forwarding(self):
        bat_path = os.path.join(REPO_ROOT, "launch.bat")
        res = subprocess.run(
            ["cmd", "/c", bat_path, "upgrade", "preview"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        assert "Hermes Upgrade Preview" in res.stdout

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    def test_unix_launch_sh_upgrade_preview_forwarding(self):
        sh_path = os.path.join(REPO_ROOT, "launch.sh")
        env = os.environ.copy()
        env["HERMES_PLATFORM"] = "linux"
        env["HERMES_ARCH"] = "x64"
        res = subprocess.run(
            [BASH_EXE, sh_path, "upgrade", "preview"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0
        assert "Hermes Upgrade Preview" in res.stdout


class TestSetupDryRun:
    @pytest.mark.skipif(not IS_WINDOWS, reason="PowerShell required on Windows")
    def test_setup_windows_dry_run(self, tmp_path):
        ps1_path = os.path.join(REPO_ROOT, "scripts", "setup-windows.ps1")
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1_path,
                "-Root",
                str(tmp_path),
                "-DryRun",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Setup windows dry run failed: {res.stderr}"
        assert "[DRY-RUN]" in res.stdout
        # Verify no actual runtimes were installed
        runtime_dir = tmp_path / ".cache" / "runtimes" / "windows-x64"
        assert not (runtime_dir / "ready.flag").exists()
        assert not (runtime_dir / "python").exists()

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix setup tests")
    @pytest.mark.parametrize("platform", ["linux", "macos"])
    def test_setup_unix_dry_run(self, tmp_path, platform):
        sh_path = os.path.join(REPO_ROOT, "scripts", "setup-unix.sh")
        env = os.environ.copy()
        env["HERMES_PLATFORM"] = platform
        env["HERMES_ARCH"] = "x64"
        env["HERMES_ARCH_OS"] = "x86_64"

        res = subprocess.run(
            [BASH_EXE, sh_path, str(tmp_path), "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0, f"Setup unix dry run failed: {res.stderr}"
        assert "[DRY‑RUN]" in res.stdout or "[DRY-RUN]" in res.stdout
        # Verify no actual runtimes were installed
        runtime_dir = tmp_path / ".cache" / "runtimes" / f"{platform}-x64"
        assert not (runtime_dir / "ready.flag").exists()
        assert not (runtime_dir / "python").exists()


class TestVaultUnlocking:
    @pytest.mark.skipif(not IS_WINDOWS, reason="PowerShell required on Windows")
    def test_unlock_vault_ps1_unencrypted(self, tmp_path):
        ps1_path = os.path.join(REPO_ROOT, "scripts", "unlock-vault.ps1")
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1_path,
                "-DataDir",
                str(tmp_path),
                "-PythonExe",
                sys.executable,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0

    @pytest.mark.skipif(not IS_WINDOWS, reason="PowerShell required on Windows")
    def test_unlock_vault_ps1_encrypted(self, tmp_path):
        sys.path.insert(0, SRC_DIR)
        from security.crypto import DataVault

        test_file = tmp_path / "secret.txt"
        test_file.write_text("top secret data", encoding="utf-8")

        vault = DataVault(str(tmp_path))
        vault.lock("smoke_password_123")
        assert vault.is_encrypted()

        ps1_path = os.path.join(REPO_ROOT, "scripts", "unlock-vault.ps1")
        env = os.environ.copy()
        env["HERMES_VAULT_PASSWORD"] = "smoke_password_123"
        env["PYTHONPATH"] = SRC_DIR

        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1_path,
                "-DataDir",
                str(tmp_path),
                "-PythonExe",
                sys.executable,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0, f"Failed: {res.stderr}"
        assert "[OK] Vault unlocked successfully!" in res.stdout
        assert not vault.is_encrypted()
        assert test_file.read_text(encoding="utf-8") == "top secret data"

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    def test_unlock_vault_sh_unencrypted(self, tmp_path):
        sh_path = os.path.join(REPO_ROOT, "scripts", "unlock-vault.sh")
        res = subprocess.run(
            [BASH_EXE, sh_path, str(tmp_path), sys.executable],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    def test_unlock_vault_sh_encrypted(self, tmp_path):
        sys.path.insert(0, SRC_DIR)
        from security.crypto import DataVault

        test_file = tmp_path / "secret.txt"
        test_file.write_text("top secret bash data", encoding="utf-8")

        vault = DataVault(str(tmp_path))
        vault.lock("bash_smoke_password")
        assert vault.is_encrypted()

        sh_path = os.path.join(REPO_ROOT, "scripts", "unlock-vault.sh")
        env = os.environ.copy()
        env["HERMES_VAULT_PASSWORD"] = "bash_smoke_password"
        env["PYTHONPATH"] = SRC_DIR

        res = subprocess.run(
            [BASH_EXE, sh_path, str(tmp_path), sys.executable],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 0, f"Failed: {res.stderr}"
        assert "[OK] Vault unlocked successfully!" in res.stdout
        assert not vault.is_encrypted()
        assert test_file.read_text(encoding="utf-8") == "top secret bash data"


class TestResetPreviews:
    @pytest.mark.skipif(not IS_WINDOWS, reason="PowerShell required on Windows")
    @pytest.mark.parametrize("mode", ["soft", "full"])
    def test_reset_windows_dry_run(self, mode):
        ps1_path = os.path.join(REPO_ROOT, "scripts", "reset-windows.ps1")
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1_path,
                "-Mode",
                mode,
                "-DryRun",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Reset windows dry run failed: {res.stderr}"
        assert "[DRY-RUN] Preview completed. No changes were made." in res.stdout

    @pytest.mark.skipif(not HAS_BASH, reason="Bash required for Unix tests")
    @pytest.mark.parametrize("mode", ["soft", "full"])
    def test_reset_unix_dry_run(self, mode):
        sh_path = os.path.join(REPO_ROOT, "scripts", "reset-unix.sh")
        res = subprocess.run(
            [BASH_EXE, sh_path, mode, "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Reset unix dry run failed: {res.stderr}"
        assert "[DRY-RUN] Preview completed. No changes were made." in res.stdout
