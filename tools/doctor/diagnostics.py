"""diagnostics.py

Diagnostic utility for the Hermes Agent Pendrive_X portable wrapper.
Inspects the platform, runtimes, virtual environment, source checkout,
data path, and optional dependencies strictly without modifying user data.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def detect_platform_info() -> Dict[str, Any]:
    os_name = platform.system()
    arch_name = platform.machine().lower()
    norm_arch = "x64" if arch_name in ("x86_64", "amd64") else ("arm64" if arch_name in ("aarch64", "arm64") else arch_name)
    
    is_windows = os_name == "Windows"
    is_macos = os_name == "Darwin"
    is_linux = os_name == "Linux"
    
    supported = False
    details = f"{os_name} {platform.release()} ({norm_arch})"
    
    if is_windows and norm_arch == "x64":
        supported = True
    elif is_macos and norm_arch in ("x64", "arm64"):
        supported = True
    elif is_linux and norm_arch in ("x64", "arm64"):
        supported = True
        
    return {
        "os": os_name,
        "release": platform.release(),
        "arch_raw": arch_name,
        "arch": norm_arch,
        "supported": supported,
        "details": details,
        "status": "PASS" if supported else "FAIL"
    }


def find_repo_root(custom_root: Optional[Path] = None) -> Path:
    if custom_root:
        return custom_root.resolve()
    # Assume tools/doctor/diagnostics.py -> parents[2] is root
    return Path(__file__).resolve().parents[2]


def get_command_version(cmd: List[str]) -> Optional[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            out = proc.stdout.strip() or proc.stderr.strip()
            return out.splitlines()[0] if out else None
    except Exception:
        pass
    return None


def inspect_runtimes(root: Path, platform_info: Dict[str, Any]) -> Dict[str, Any]:
    cache_dir = root / ".cache"
    runtimes_dir = cache_dir / "runtimes"
    
    os_slug = "windows" if platform_info["os"] == "Windows" else ("macos" if platform_info["os"] == "Darwin" else "linux")
    plat_key = f"{os_slug}-{platform_info['arch']}"
    target_runtime_dir = runtimes_dir / plat_key
    
    manifest_file = target_runtime_dir / "manifest.json"
    manifest_data = None
    manifest_status = "MISSING"
    if manifest_file.exists():
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest_status = "VALID"
        except Exception as exc:
            manifest_status = f"CORRUPTED: {exc}"
            
    # Binary locations
    is_win = platform_info["os"] == "Windows"
    py_bin = target_runtime_dir / ("python/python.exe" if is_win else "python/bin/python3")
    node_bin = target_runtime_dir / ("node/node.exe" if is_win else "node/bin/node")
    uv_bin = target_runtime_dir / ("uv/uv.exe" if is_win else "uv/uv")
    rg_bin = target_runtime_dir / ("bin/rg.exe" if is_win else "bin/rg")
    git_bin = target_runtime_dir / ("bin/git.exe" if is_win else "bin/git")
    
    results: Dict[str, Any] = {
        "runtime_dir": str(target_runtime_dir),
        "runtime_exists": target_runtime_dir.exists(),
        "ready_flag": (target_runtime_dir / "ready.flag").exists(),
        "manifest_status": manifest_status,
        "manifest": manifest_data,
        "components": {}
    }
    
    # Python
    py_ver = get_command_version([str(py_bin), "--version"]) if py_bin.exists() else None
    results["components"]["python"] = {
        "path": str(py_bin),
        "exists": py_bin.exists(),
        "version": py_ver,
        "status": "PASS" if py_ver else ("WARN" if not target_runtime_dir.exists() else "FAIL")
    }
    
    # Node
    node_ver = get_command_version([str(node_bin), "--version"]) if node_bin.exists() else None
    results["components"]["node"] = {
        "path": str(node_bin),
        "exists": node_bin.exists(),
        "version": node_ver,
        "status": "PASS" if node_ver else "WARN"
    }
    
    # uv
    uv_ver = get_command_version([str(uv_bin), "--version"]) if uv_bin.exists() else None
    results["components"]["uv"] = {
        "path": str(uv_bin),
        "exists": uv_bin.exists(),
        "version": uv_ver,
        "status": "PASS" if uv_ver else "WARN"
    }
    
    # ripgrep
    rg_ver = get_command_version([str(rg_bin), "--version"]) if rg_bin.exists() else None
    results["components"]["ripgrep"] = {
        "path": str(rg_bin),
        "exists": rg_bin.exists(),
        "version": rg_ver,
        "status": "PASS" if rg_ver else "WARN"
    }
    
    # git (Windows portable or host)
    git_ver = None
    if git_bin.exists():
        git_ver = get_command_version([str(git_bin), "--version"])
    elif shutil.which("git"):
        git_ver = get_command_version(["git", "--version"])
        
    results["components"]["git"] = {
        "path": str(git_bin) if git_bin.exists() else (shutil.which("git") or "not found"),
        "exists": git_bin.exists() or bool(shutil.which("git")),
        "version": git_ver,
        "status": "PASS" if git_ver else "WARN"
    }
    
    return results


def inspect_virtual_env(root: Path, platform_info: Dict[str, Any]) -> Dict[str, Any]:
    os_slug = "windows" if platform_info["os"] == "Windows" else ("macos" if platform_info["os"] == "Darwin" else "linux")
    plat_key = f"{os_slug}-{platform_info['arch']}"
    runtime_dir = root / ".cache" / "runtimes" / plat_key
    
    # Check venv.path pointer or default venv location
    venv_pointer = runtime_dir / "venv.path"
    if venv_pointer.exists():
        try:
            venv_dir = Path(venv_pointer.read_text(encoding="utf-8").strip())
        except Exception:
            venv_dir = runtime_dir / "venv"
    else:
        venv_dir = runtime_dir / "venv"
        
    is_win = platform_info["os"] == "Windows"
    py_exe = venv_dir / ("Scripts/python.exe" if is_win else "bin/python")
    cfg_file = venv_dir / "pyvenv.cfg"
    activate_file = venv_dir / ("Scripts/activate.bat" if is_win else "bin/activate")
    
    exists = venv_dir.is_dir()
    py_exists = py_exe.exists()
    cfg_exists = cfg_file.exists()
    
    py_ver = None
    if py_exists:
        py_ver = get_command_version([str(py_exe), "--version"])
        
    status = "PASS" if (exists and py_exists and cfg_exists) else ("MISSING" if not exists else "WARN")
    
    return {
        "venv_dir": str(venv_dir),
        "exists": exists,
        "python_executable": str(py_exe),
        "python_exists": py_exists,
        "python_version": py_ver,
        "pyvenv_cfg_exists": cfg_exists,
        "activate_script_exists": activate_file.exists(),
        "status": status
    }


def inspect_source_checkout(root: Path) -> Dict[str, Any]:
    hermes_src = root / "src" / "hermes-agent"
    exists = hermes_src.is_dir()
    
    is_git_repo = (hermes_src / ".git").is_dir()
    git_head = None
    if is_git_repo:
        try:
            head_file = hermes_src / ".git" / "HEAD"
            if head_file.exists():
                git_head = head_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
            
    version = None
    cli_init = hermes_src / "hermes_cli" / "__init__.py"
    if cli_init.exists():
        try:
            txt = cli_init.read_text(encoding="utf-8")
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', txt)
            if m:
                version = m.group(1)
        except Exception:
            pass
            
    security_src = root / "src" / "security"
    security_exists = security_src.is_dir()
    
    status = "PASS" if exists and security_exists else ("WARN" if not exists else "FAIL")
    
    return {
        "hermes_src": str(hermes_src),
        "exists": exists,
        "is_git_repo": is_git_repo,
        "git_head": git_head,
        "version": version or "unknown",
        "security_package_exists": security_exists,
        "status": status
    }


def inspect_data_path(root: Path, custom_data_dir: Optional[Path] = None) -> Dict[str, Any]:
    data_dir = custom_data_dir.resolve() if custom_data_dir else (root / "data")
    exists = data_dir.is_dir()
    
    # Read-only checks: strictly DO NOT create or modify files!
    readable = os.access(data_dir, os.R_OK) if exists else False
    writable = os.access(data_dir, os.W_OK) if exists else False
    
    env_file = data_dir / ".env"
    config_file = data_dir / "config.yaml"
    
    env_configured = False
    if env_file.is_file():
        try:
            lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for ln in lines:
                s = ln.strip()
                if s and not s.startswith("#") and "=" in s:
                    env_configured = True
                    break
        except Exception:
            pass
            
    config_exists = config_file.is_file()
    
    # Vault inspection (read-only scan)
    encrypted_files: List[str] = []
    plaintext_files: List[str] = []
    if exists and readable:
        try:
            for p in data_dir.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    # Check if file has vault envelope without modifying
                    try:
                        head = p.read_bytes()[:128]
                        if b'"vault_version"' in head or b'"ciphertext"' in head:
                            encrypted_files.append(str(p.relative_to(data_dir)))
                        else:
                            plaintext_files.append(str(p.relative_to(data_dir)))
                    except Exception:
                        pass
        except Exception:
            pass
            
    status = "PASS" if exists and readable else ("WARN" if not exists else "FAIL")
    
    return {
        "data_dir": str(data_dir),
        "exists": exists,
        "readable": readable,
        "writable": writable,
        "env_file_exists": env_file.is_file(),
        "env_configured": env_configured,
        "config_file_exists": config_exists,
        "vault_encrypted_files_count": len(encrypted_files),
        "vault_encrypted_sample": encrypted_files[:5],
        "plaintext_files_count": len(plaintext_files),
        "status": status
    }


def inspect_optional_dependencies(root: Path, venv_info: Dict[str, Any]) -> Dict[str, Any]:
    deps: Dict[str, Any] = {}
    
    # Cryptography
    try:
        import cryptography
        deps["cryptography"] = {"available": True, "version": getattr(cryptography, "__version__", "installed"), "status": "PASS"}
    except ImportError:
        deps["cryptography"] = {"available": False, "version": None, "status": "WARN"}
        
    # YubiKey Manager
    ykman_which = shutil.which("ykman")
    deps["yubikey_manager"] = {
        "available": bool(ykman_which),
        "path": ykman_which,
        "status": "PASS" if ykman_which else "INFO"
    }
    
    # Playwright
    try:
        import playwright
        deps["playwright_python"] = {"available": True, "version": getattr(playwright, "__version__", "installed"), "status": "PASS"}
    except ImportError:
        deps["playwright_python"] = {"available": False, "version": None, "status": "INFO"}
        
    # Python Telegram Bot
    try:
        import telegram
        deps["telegram_bot"] = {"available": True, "version": getattr(telegram, "__version__", "installed"), "status": "PASS"}
    except ImportError:
        deps["telegram_bot"] = {"available": False, "version": None, "status": "INFO"}
        
    # boto3 (for S3 Sync)
    try:
        import boto3
        deps["boto3"] = {"available": True, "version": getattr(boto3, "__version__", "installed"), "status": "PASS"}
    except ImportError:
        deps["boto3"] = {"available": False, "version": None, "status": "INFO"}
        
    # Electron GUI
    electron_dir = root / "gui" / "electron"
    electron_exists = (electron_dir / "package.json").is_file()
    deps["electron_launcher"] = {
        "available": electron_exists,
        "path": str(electron_dir) if electron_exists else None,
        "status": "PASS" if electron_exists else "INFO"
    }
    
    return deps


def run_diagnostics(root: Optional[Path] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    repo_root = find_repo_root(root)
    platform_info = detect_platform_info()
    runtimes_info = inspect_runtimes(repo_root, platform_info)
    venv_info = inspect_virtual_env(repo_root, platform_info)
    source_info = inspect_source_checkout(repo_root)
    data_info = inspect_data_path(repo_root, data_dir)
    optional_deps = inspect_optional_dependencies(repo_root, venv_info)
    
    # Compute summary
    statuses: List[str] = [platform_info["status"]]
    for comp in runtimes_info["components"].values():
        statuses.append(comp["status"])
    statuses.append(venv_info["status"])
    statuses.append(source_info["status"])
    statuses.append(data_info["status"])
    
    fail_count = sum(1 for s in statuses if s == "FAIL")
    warn_count = sum(1 for s in statuses if s in ("WARN", "MISSING"))
    pass_count = sum(1 for s in statuses if s == "PASS")
    
    overall = "HEALTHY" if fail_count == 0 and warn_count == 0 else ("WARNING" if fail_count == 0 else "ERROR")
    
    return {
        "overall_status": overall,
        "summary": {
            "passed": pass_count,
            "warnings": warn_count,
            "failed": fail_count
        },
        "repo_root": str(repo_root),
        "platform": platform_info,
        "runtimes": runtimes_info,
        "virtual_environment": venv_info,
        "source_checkout": source_info,
        "data_path": data_info,
        "optional_dependencies": optional_deps
    }


def print_cli_report(diag: Dict[str, Any], no_color: bool = False) -> None:
    c_rst = "" if no_color else "\033[0m"
    c_grn = "" if no_color else "\033[32m"
    c_yel = "" if no_color else "\033[33m"
    c_red = "" if no_color else "\033[31m"
    c_cyn = "" if no_color else "\033[36m"
    c_bld = "" if no_color else "\033[1m"
    
    def tag(s: str) -> str:
        if s == "PASS":
            return f"{c_grn}[PASS]{c_rst}"
        if s in ("WARN", "MISSING"):
            return f"{c_yel}[WARN]{c_rst}"
        if s == "INFO":
            return f"{c_cyn}[INFO]{c_rst}"
        return f"{c_red}[FAIL]{c_rst}"
        
    print(f"\n{c_bld}============================================================{c_rst}")
    print(f"{c_bld}  Hermes Pendrive_X - Portable Wrapper Diagnostics{c_rst}")
    print(f"{c_bld}============================================================{c_rst}\n")
    
    p = diag["platform"]
    print(f"{c_cyn}1. Host Platform:{c_rst}")
    print(f"   {tag(p['status'])} OS / Architecture: {p['details']} (Supported: {p['supported']})")
    
    rt = diag["runtimes"]
    print(f"\n{c_cyn}2. Runtime Components:{c_rst} (Runtime Dir: {rt['runtime_dir']})")
    print(f"   Ready flag present: {rt['ready_flag']}, Manifest: {rt['manifest_status']}")
    for name, comp in rt["components"].items():
        ver_str = comp["version"] or ("not installed" if not comp["exists"] else "installed")
        print(f"   {tag(comp['status'])} {name.capitalize():<12}: {ver_str} ({comp['path']})")
        
    v = diag["virtual_environment"]
    print(f"\n{c_cyn}3. Virtual Environment:{c_rst}")
    print(f"   {tag(v['status'])} Venv path: {v['venv_dir']}")
    print(f"   Python binary: {v['python_executable']} (Exists: {v['python_exists']}, Version: {v['python_version'] or 'N/A'})")
    print(f"   pyvenv.cfg: {v['pyvenv_cfg_exists']}, Activation scripts: {v['activate_script_exists']}")
    
    s = diag["source_checkout"]
    print(f"\n{c_cyn}4. Source Checkout:{c_rst}")
    print(f"   {tag(s['status'])} Hermes Source: {s['hermes_src']} (Exists: {s['exists']}, Version: {s['version']})")
    print(f"   Git Repository: {s['is_git_repo']} (HEAD: {s['git_head'] or 'N/A'})")
    print(f"   Security package (src/security): {'Present' if s['security_package_exists'] else 'Missing'}")
    
    d = diag["data_path"]
    print(f"\n{c_cyn}5. Data Path (Read-Only Inspection):{c_rst}")
    print(f"   {tag(d['status'])} Location: {d['data_dir']} (Readable: {d['readable']}, Writable: {d['writable']})")
    print(f"   Configuration: .env present={d['env_file_exists']} (Configured={d['env_configured']}), config.yaml={d['config_file_exists']}")
    print(f"   Vault files: {d['vault_encrypted_files_count']} encrypted, {d['plaintext_files_count']} plaintext files")
    
    print(f"\n{c_cyn}6. Optional Dependencies:{c_rst}")
    for name, dep in diag["optional_dependencies"].items():
        st = dep["status"]
        avail = "available" if dep["available"] else "not installed"
        ver = f" (v{dep['version']})" if dep.get("version") and dep["version"] != "installed" else ""
        print(f"   {tag(st)} {name.replace('_', ' ').title():<22}: {avail}{ver}")
        
    summary = diag["summary"]
    print(f"\n{c_bld}------------------------------------------------------------{c_rst}")
    print(f"Summary: {c_grn}{summary['passed']} passed{c_rst}, {c_yel}{summary['warnings']} warnings{c_rst}, {c_red}{summary['failed']} failed{c_rst} (Overall: {diag['overall_status']})")
    print(f"{c_bld}------------------------------------------------------------{c_rst}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect platform, runtimes, virtualenv, source, data path, and dependencies without modifying user data."
    )
    parser.add_argument("--root", type=Path, default=None, help="Repository root path")
    parser.add_argument("--data-dir", type=Path, default=None, help="Custom data directory to inspect")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="Disable colored console output")
    args = parser.parse_args()
    
    diag = run_diagnostics(root=args.root, data_dir=args.data_dir)
    
    if args.json:
        print(json.dumps(diag, indent=2))
    else:
        print_cli_report(diag, no_color=args.no_color)
        
    # Return 0 if platform supported and no critical failure
    return 1 if diag["platform"]["status"] == "FAIL" or diag["summary"]["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
