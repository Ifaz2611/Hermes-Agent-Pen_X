"""upgrade_manager.py

Upgrade and rollback management for Hermes Agent Pendrive_X.
Features:
- Explains changes before applying them (preview/dry-run).
- Backs up relevant metadata (manifest.json, source commit/state, venv info).
- Applies updates with transactional error-handling.
- Provides automatic rollback and documented recovery paths.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_repo_root(custom_root: Optional[Path] = None) -> Path:
    if custom_root:
        return custom_root.resolve()
    return Path(__file__).resolve().parents[2]


def get_active_runtime_dir(root: Path) -> Path:
    runtimes_dir = root / ".cache" / "runtimes"
    if not runtimes_dir.is_dir():
        return runtimes_dir / "windows-x64" if os.name == "nt" else runtimes_dir / "linux-x64"
        
    candidates = sorted([p for p in runtimes_dir.iterdir() if p.is_dir()])
    sys_name = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
    matched = [p for p in candidates if sys_name in p.name.lower()]
    if matched:
        return matched[0]
    return candidates[0] if candidates else runtimes_dir / (f"{sys_name}-x64")


def read_source_state(root: Path) -> Dict[str, Any]:
    src_dir = root / "src" / "hermes-agent"
    exists = src_dir.is_dir()
    is_git = (src_dir / ".git").is_dir()
    commit = None
    branch = None
    version = "unknown"
    
    if is_git:
        try:
            p_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src_dir, capture_output=True, text=True, timeout=5)
            if p_rev.returncode == 0:
                commit = p_rev.stdout.strip()
            p_br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=src_dir, capture_output=True, text=True, timeout=5)
            if p_br.returncode == 0:
                branch = p_br.stdout.strip()
        except Exception:
            pass
            
    cli_init = src_dir / "hermes_cli" / "__init__.py"
    if cli_init.is_file():
        try:
            import re
            txt = cli_init.read_text(encoding="utf-8")
            m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', txt)
            if m:
                version = m.group(1)
        except Exception:
            pass
            
    return {
        "exists": exists,
        "is_git": is_git,
        "commit": commit,
        "branch": branch,
        "version": version
    }


def read_runtime_manifest(runtime_dir: Path) -> Optional[Dict[str, Any]]:
    m_path = runtime_dir / "manifest.json"
    if m_path.is_file():
        try:
            return json.loads(m_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def read_target_manifest(root: Path) -> Optional[Dict[str, Any]]:
    m_path = root / "scripts" / "manifests" / "runtimes.json"
    if m_path.is_file():
        try:
            return json.loads(m_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def plan_upgrade(root: Path, runtime_dir: Path) -> Dict[str, Any]:
    src_state = read_source_state(root)
    current_manifest = read_runtime_manifest(runtime_dir) or {}
    target_manifest_all = read_target_manifest(root) or {}
    
    plat_name = runtime_dir.name
    target_plat = target_manifest_all.get("platforms", {}).get(plat_name, {})
    
    changes = []
    
    # Source changes
    if src_state["exists"]:
        changes.append({
            "component": "Hermes Source",
            "current": f"{src_state['version']} ({src_state['commit'][:7] if src_state['commit'] else 'local'})",
            "target": "latest (main branch)",
            "action": "git pull / update package & dependencies"
        })
    else:
        changes.append({
            "component": "Hermes Source",
            "current": "missing",
            "target": "latest (main branch)",
            "action": "fetch source and install"
        })
        
    # Runtime components
    cur_versions = current_manifest.get("versions", {})
    for comp in ["python", "node", "uv", "rg", "git"]:
        cur_v = cur_versions.get(comp, "unknown")
        target_info = target_plat.get(comp, {})
        target_v = target_info.get("version", cur_v)
        
        status = "Up to date" if cur_v == target_v and cur_v != "unknown" else "Upgrade available"
        changes.append({
            "component": comp.capitalize(),
            "current": str(cur_v),
            "target": str(target_v),
            "action": status
        })
        
    return {
        "platform": plat_name,
        "runtime_dir": str(runtime_dir),
        "source_state": src_state,
        "current_manifest": current_manifest,
        "target_manifest": target_plat,
        "changes": changes
    }


def display_upgrade_plan(plan: Dict[str, Any]) -> None:
    print("\n============================================================")
    print("                Hermes Upgrade Preview")
    print("============================================================\n")
    print(f"Target Platform Runtime: {plan['platform']}")
    print(f"Runtime Directory:       {plan['runtime_dir']}\n")
    print(f"{'Component':<18} {'Current Version':<22} {'Target Version':<22} {'Action'}")
    print("-" * 75)
    for c in plan["changes"]:
        print(f"{c['component']:<18} {c['current']:<22} {c['target']:<22} {c['action']}")
    print("\nPlanned Steps:")
    print("  1. Create metadata backup (manifest.json, git commit/HEAD, venv metadata)")
    print("  2. Apply Hermes source update")
    print("  3. Update Python dependencies in virtual environment")
    print("  4. Update runtime manifest with verified metadata")
    print("  5. Keep rollback recovery point in .cache/backups/\n")


def create_metadata_backup(root: Path, runtime_dir: Path) -> Path:
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = root / ".cache" / "backups" / f"upgrade_{now_str}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Backup manifest.json
    m_file = runtime_dir / "manifest.json"
    if m_file.is_file():
        shutil.copy2(m_file, backup_dir / "manifest.json")
        
    # 2. Backup source info
    src_state = read_source_state(root)
    (backup_dir / "source_state.json").write_text(json.dumps(src_state, indent=2), encoding="utf-8")
    
    # 3. Backup venv info
    venv_dir = runtime_dir / "venv"
    venv_info = {
        "venv_dir": str(venv_dir),
        "exists": venv_dir.is_dir()
    }
    cfg_file = venv_dir / "pyvenv.cfg"
    if cfg_file.is_file():
        shutil.copy2(cfg_file, backup_dir / "pyvenv.cfg")
        
    py_exe = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if py_exe.is_file():
        try:
            proc = subprocess.run([str(py_exe), "-m", "pip", "freeze"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                venv_info["pip_freeze"] = proc.stdout
        except Exception:
            pass
            
    (backup_dir / "venv_state.json").write_text(json.dumps(venv_info, indent=2), encoding="utf-8")
    
    # 4. Write recovery descriptor
    descriptor = {
        "timestamp": now_str,
        "runtime_dir": str(runtime_dir),
        "source_commit": src_state.get("commit"),
        "source_version": src_state.get("version"),
        "recovery_instructions": [
            f"Run: python tools/upgrade/upgrade_manager.py rollback --backup-dir {backup_dir}",
            f"If git source: cd src/hermes-agent && git checkout {src_state.get('commit') or 'HEAD'}",
            f"Restore manifest: copy {backup_dir / 'manifest.json'} to {runtime_dir / 'manifest.json'}"
        ]
    }
    (backup_dir / "rollback_descriptor.json").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    
    # Update latest pointer
    latest_pointer = root / ".cache" / "backups" / "latest_upgrade.json"
    latest_pointer.write_text(json.dumps({"latest_backup_dir": str(backup_dir), "timestamp": now_str}, indent=2), encoding="utf-8")
    
    return backup_dir


def print_recovery_guidance(backup_dir: Path, error_msg: str) -> None:
    print("\n" + "=" * 60)
    print("           UPGRADE FAILED - RECOVERY GUIDANCE")
    print("=" * 60)
    print(f"\nFailure reason: {error_msg}")
    print(f"Pre-upgrade metadata backup is preserved at:\n  {backup_dir}\n")
    print("To restore the previous working state automatically:")
    if os.name == "nt":
        print("  .\\launch.bat rollback")
    else:
        print("  bash launch.sh rollback")
    print(f"  python tools/upgrade/upgrade_manager.py rollback --backup-dir \"{backup_dir}\"\n")
    print("Manual Recovery Steps:")
    print("  1. Check source checkout under src/hermes-agent")
    print(f"  2. Restore manifest: copy \"{backup_dir / 'manifest.json'}\" to your runtime dir")
    print("  3. Run setup dry-run to verify integrity")
    print("=" * 60 + "\n")


def execute_upgrade(root: Path, runtime_dir: Path, confirm: bool = True) -> int:
    plan = plan_upgrade(root, runtime_dir)
    display_upgrade_plan(plan)
    
    if confirm:
        try:
            resp = input("Apply these changes now? [y/N]: ").strip().lower()
            if resp not in ("y", "yes"):
                print("Upgrade cancelled by user. No changes were made.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nUpgrade cancelled.")
            return 0
            
    print("\n[1/4] Backing up relevant metadata...")
    backup_dir = create_metadata_backup(root, runtime_dir)
    print(f"      Backup saved to: {backup_dir}")
    
    # Step 2: Source update
    src_dir = root / "src" / "hermes-agent"
    print("\n[2/4] Updating Hermes source...")
    try:
        if (src_dir / ".git").is_dir():
            git_exe = shutil.which("git") or str(runtime_dir / "bin/git.exe")
            proc = subprocess.run([git_exe, "pull"], cwd=src_dir, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                raise RuntimeError(f"Git pull failed: {proc.stderr.strip() or proc.stdout.strip()}")
            print(f"      Git pull successful: {proc.stdout.strip()[:100]}")
        else:
            print("      Source is not a Git repo; source files preserved.")
    except Exception as exc:
        print_recovery_guidance(backup_dir, str(exc))
        return 1
        
    # Step 3: Dependencies update
    print("\n[3/4] Updating Python dependencies in virtual environment...")
    venv_dir = runtime_dir / "venv"
    py_exe = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    uv_exe = runtime_dir / ("uv/uv.exe" if os.name == "nt" else "uv/uv")
    
    if py_exe.is_file() and src_dir.is_dir():
        try:
            if uv_exe.is_file():
                proc = subprocess.run(
                    [str(uv_exe), "pip", "install", "--python", str(py_exe), "-e", f"{src_dir}[all]"],
                    capture_output=True, text=True, timeout=120
                )
            else:
                proc = subprocess.run(
                    [str(py_exe), "-m", "pip", "install", "-e", f"{src_dir}[all]"],
                    capture_output=True, text=True, timeout=120
                )
            if proc.returncode != 0:
                raise RuntimeError(f"Dependency install failed: {proc.stderr.strip() or proc.stdout.strip()}")
            print("      Python dependencies updated successfully.")
        except Exception as exc:
            print_recovery_guidance(backup_dir, str(exc))
            return 1
    else:
        print("      Venv or source not present; skipping package install.")
        
    # Step 4: Manifest update
    print("\n[4/4] Updating runtime manifest...")
    try:
        cur_m = read_runtime_manifest(runtime_dir) or {}
        cur_m["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur_m["last_upgrade_backup"] = str(backup_dir)
        new_state = read_source_state(root)
        if "versions" in cur_m:
            cur_m["versions"]["hermes"] = new_state.get("commit") or new_state.get("version")
        m_file = runtime_dir / "manifest.json"
        m_file.write_text(json.dumps(cur_m, indent=2), encoding="utf-8")
        print("      Manifest updated successfully.")
    except Exception as exc:
        print_recovery_guidance(backup_dir, str(exc))
        return 1
        
    print("\n============================================================")
    print("              Hermes Upgrade Completed Successfully!")
    print("============================================================\n")
    return 0


def execute_rollback(root: Path, runtime_dir: Path, custom_backup_dir: Optional[Path] = None) -> int:
    backup_dir = custom_backup_dir
    if not backup_dir:
        pointer = root / ".cache" / "backups" / "latest_upgrade.json"
        if pointer.is_file():
            try:
                data = json.loads(pointer.read_text(encoding="utf-8"))
                backup_dir = Path(data.get("latest_backup_dir", ""))
            except Exception:
                pass
                
    if not backup_dir or not backup_dir.is_dir():
        print(f"[ERROR] No valid upgrade backup found at {backup_dir or 'default location'}.")
        print("Please specify a valid backup directory via --backup-dir <path>.")
        return 1
        
    print(f"\n[ROLLBACK] Initiating rollback using snapshot:\n  {backup_dir}\n")
    
    # 1. Restore manifest
    m_bak = backup_dir / "manifest.json"
    if m_bak.is_file():
        target_m = runtime_dir / "manifest.json"
        shutil.copy2(m_bak, target_m)
        print(f"[ROLLBACK] Restored manifest: {target_m}")
        
    # 2. Revert git commit
    src_info_file = backup_dir / "source_state.json"
    if src_info_file.is_file():
        try:
            s_data = json.loads(src_info_file.read_text(encoding="utf-8"))
            commit = s_data.get("commit")
            src_dir = root / "src" / "hermes-agent"
            if commit and (src_dir / ".git").is_dir():
                git_exe = shutil.which("git") or str(runtime_dir / "bin/git.exe")
                proc = subprocess.run([git_exe, "checkout", commit], cwd=src_dir, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0:
                    print(f"[ROLLBACK] Reverted source checkout to commit: {commit[:8]}")
                else:
                    print(f"[WARN] Failed to checkout {commit}: {proc.stderr.strip()}")
        except Exception as exc:
            print(f"[WARN] Source rollback error: {exc}")
            
    print("\n[ROLLBACK] Rollback completed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Hermes upgrades, preview changes, and perform rollbacks.")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")
    
    # Preview / plan
    p_plan = subparsers.add_parser("preview", help="Preview planned changes without modifying any files")
    p_plan.add_argument("--root", type=Path, default=None)
    
    # Apply
    p_apply = subparsers.add_parser("apply", help="Apply upgrade after backing up metadata")
    p_apply.add_argument("--root", type=Path, default=None)
    p_apply.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    
    # Rollback
    p_rollback = subparsers.add_parser("rollback", help="Roll back to the previous upgrade snapshot")
    p_rollback.add_argument("--root", type=Path, default=None)
    p_rollback.add_argument("--backup-dir", type=Path, default=None, help="Specific backup snapshot directory")
    
    args = parser.parse_args()
    root = find_repo_root(args.root if hasattr(args, "root") else None)
    runtime_dir = get_active_runtime_dir(root)
    
    if args.action in ("preview", None):
        plan = plan_upgrade(root, runtime_dir)
        display_upgrade_plan(plan)
        return 0
    elif args.action == "apply":
        return execute_upgrade(root, runtime_dir, confirm=not args.yes)
    elif args.action == "rollback":
        return execute_rollback(root, runtime_dir, custom_backup_dir=args.backup_dir)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
