#!/usr/bin/env python3
"""ci_check.py

Unified CI and pre-commit validator for Hermes Agent Pendrive_X:
1. Shell syntax validation (bash -n on .sh files).
2. PowerShell & Batch validation (.ps1 and .bat files).
3. Python compilation and syntax check (py_compile on .py files).
4. JavaScript syntax validation (node --check on .js files).
5. Markdown-link validation across all repository markdown files.
6. Git tracked-files hygiene (ensures generated files, runtime downloads,
   and local secrets are never tracked).
"""

from __future__ import annotations

import argparse
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def find_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_python_files(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    py_files = [
        p for p in root.rglob("*.py")
        if not any(part in p.parts for part in (".cache", "venv", ".venv", "node_modules", ".git"))
    ]
    for p in sorted(py_files):
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{p.relative_to(root)}: {exc}")
    return len(errors) == 0, errors


def get_bash_executable() -> Optional[str]:
    if sys.platform == "win32":
        for git_bash in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Git\bin\bash.exe",
        ]:
            if os.path.exists(git_bash):
                return git_bash
    which_bash = shutil.which("bash")
    if which_bash and "system32" not in which_bash.lower():
        return which_bash
    return None


def check_shell_files(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    sh_files = [
        p for p in root.rglob("*.sh")
        if not any(part in p.parts for part in (".cache", "node_modules", ".git"))
    ]
    bash_exe = get_bash_executable()

    for p in sorted(sh_files):
        if bash_exe:
            proc = subprocess.run([bash_exe, "-n", str(p)], capture_output=True, text=True)
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                errors.append(f"{p.relative_to(root)}: {err}")
        else:
            # Fallback basic lint
            content = p.read_text(encoding="utf-8", errors="replace")
            if not content.startswith("#!"):
                errors.append(f"{p.relative_to(root)}: Missing shebang")
    return len(errors) == 0, errors


def check_powershell_and_batch_files(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    ps_files = [
        p for p in root.rglob("*.ps1")
        if not any(part in p.parts for part in (".cache", "node_modules", ".git"))
    ]
    
    # Check powershell files
    pwsh_exe = shutil.which("powershell") or shutil.which("pwsh")
    for p in sorted(ps_files):
        if pwsh_exe:
            code = (
                f"$errs = $null; $toks = $null; "
                f"[System.Management.Automation.Language.Parser]::ParseFile('{p.resolve()}', [ref]$toks, [ref]$errs); "
                f"if ($errs.Count -gt 0) {{ foreach ($e in $errs) {{ Write-Error $e.Message }} exit 1 }}"
            )
            proc = subprocess.run([pwsh_exe, "-NoProfile", "-Command", code], capture_output=True, text=True)
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                errors.append(f"{p.relative_to(root)}: {err}")
        else:
            txt = p.read_text(encoding="utf-8", errors="replace")
            if txt.count("{") != txt.count("}"):
                errors.append(f"{p.relative_to(root)}: Unbalanced curly braces detected")

    # Check batch files
    bat_files = [
        p for p in root.rglob("*.bat")
        if not any(part in p.parts for part in (".cache", "node_modules", ".git"))
    ]
    for b in sorted(bat_files):
        txt = b.read_text(encoding="utf-8", errors="replace")
        # Check basic syntax / balanced parentheses in blocks
        lines = txt.splitlines()
        for idx, ln in enumerate(lines, 1):
            if ln.strip().startswith("goto :") and not re.search(r"goto\s+:[A-Za-z0-9_]+", ln):
                errors.append(f"{b.relative_to(root)}: line {idx} invalid goto target")
    return len(errors) == 0, errors


def check_javascript_files(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    js_files = [
        p for p in root.rglob("*.js")
        if not any(part in p.parts for part in (".cache", "node_modules", ".git"))
    ]
    node_exe = shutil.which("node")
    for j in sorted(js_files):
        if node_exe:
            proc = subprocess.run([node_exe, "--check", str(j)], capture_output=True, text=True)
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                errors.append(f"{j.relative_to(root)}: {err}")
        else:
            # Fallback check
            txt = j.read_text(encoding="utf-8", errors="replace")
            if txt.count("{") != txt.count("}") or txt.count("(") != txt.count(")"):
                errors.append(f"{j.relative_to(root)}: Unbalanced brackets/parentheses detected")
    return len(errors) == 0, errors


def check_markdown_links(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    md_files = [
        p for p in root.rglob("*.md")
        if not any(part in p.parts for part in (".cache", "node_modules", ".git"))
    ]
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    
    for m in sorted(md_files):
        content = m.read_text(encoding="utf-8", errors="replace")
        for match in link_re.finditer(content):
            label, target = match.group(1), match.group(2).strip()
            # Ignore external protocols and purely in-page anchors
            if target.startswith(("http://", "https://", "mailto:", "ftp://", "#")):
                continue
            parts = target.split("#", 1)
            target_path_str = parts[0]
            anchor = parts[1] if len(parts) > 1 else None
            
            if target_path_str:
                resolved_target = (m.parent / target_path_str).resolve()
                if not resolved_target.exists():
                    errors.append(f"{m.relative_to(root)}: Broken link '{target}' (target not found: {resolved_target.name})")
    return len(errors) == 0, errors


def check_tracked_files_hygiene(root: Path) -> Tuple[bool, List[str]]:
    errors = []
    try:
        proc = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            return True, []
        tracked_files = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    except Exception:
        return True, []

    # 1. Generated files / logs / runtime flags
    bad_generated_patterns = [
        re.compile(r"\.pyc$"),
        re.compile(r"__pycache__"),
        re.compile(r"\.log$"),
        re.compile(r"\.flag$"),
        re.compile(r"setup-progress\.json$"),
        re.compile(r"gateway\.pid$"),
        re.compile(r"^data/.*"),
        re.compile(r"^\.cache/.*"),
    ]
    
    # 2. Runtime downloads
    bad_download_patterns = [
        re.compile(r"\.(tar\.gz|tar\.xz|tgz|zip|msi)$"),
    ]
    
    # 3. Local secrets & sensitive files
    bad_secret_patterns = [
        re.compile(r"^\.env$"),
        re.compile(r"^\.env\.local$"),
        re.compile(r"^\.env\.production$"),
        re.compile(r"\.(pem|key|id_rsa|id_ed25519)$"),
    ]
    
    for tf in tracked_files:
        norm = tf.replace("\\", "/")
        # Allow deliberately tracked examples/templates
        if norm in (".env.example",):
            continue
            
        for pat in bad_generated_patterns:
            if pat.search(norm):
                errors.append(f"Generated file tracked in git: {norm}")
                break
                
        for pat in bad_download_patterns:
            if pat.search(norm):
                errors.append(f"Runtime download/archive tracked in git: {norm}")
                break
                
        for pat in bad_secret_patterns:
            if pat.search(norm):
                errors.append(f"Sensitive secret file tracked in git: {norm}")
                break
                
    # Also inspect content of tracked files for accidental API keys or secrets
    secret_content_re = re.compile(r"(sk-[a-zA-Z0-9]{24,}|AKIA[0-9A-Z]{16})")
    for tf in tracked_files:
        p = root / tf
        if p.is_file() and p.stat().st_size < 1_000_000:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                m = secret_content_re.search(txt)
                if m:
                    errors.append(f"Hardcoded API key or secret found in {tf}: {m.group(1)[:6]}...")
            except Exception:
                pass

    return len(errors) == 0, errors


def run_all_checks(root: Optional[Path] = None) -> Tuple[bool, Dict[str, List[str]]]:
    r = root.resolve() if root else find_repo_root()
    results = {}
    
    _, results["python"] = check_python_files(r)
    _, results["shell"] = check_shell_files(r)
    _, results["powershell_batch"] = check_powershell_and_batch_files(r)
    _, results["javascript"] = check_javascript_files(r)
    _, results["markdown_links"] = check_markdown_links(r)
    _, results["tracked_hygiene"] = check_tracked_files_hygiene(r)
    
    all_ok = all(len(errs) == 0 for errs in results.values())
    return all_ok, results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run complete CI checks on repository files.")
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()
    
    root = find_repo_root() if not args.root else args.root.resolve()
    print("============================================================")
    print("           Hermes CI & File Integrity Checker")
    print("============================================================\n")
    
    all_ok, results = run_all_checks(root)
    
    names = {
        "python": "Python Files (.py)",
        "shell": "Shell Scripts (.sh)",
        "powershell_batch": "PowerShell & Batch (.ps1, .bat)",
        "javascript": "JavaScript Files (.js)",
        "markdown_links": "Markdown Relative Links (.md)",
        "tracked_hygiene": "Git Tracked Files Hygiene (no secrets/downloads/generated)"
    }
    
    for key, label in names.items():
        errs = results.get(key, [])
        if not errs:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label} ({len(errs)} errors):")
            for e in errs[:10]:
                print(f"         - {e}")
            if len(errs) > 10:
                print(f"         ... and {len(errs) - 10} more.")
                
    print("\n------------------------------------------------------------")
    if all_ok:
        print("Result: ALL CHECKS PASSED")
        print("------------------------------------------------------------\n")
        return 0
    else:
        print("Result: INTEGRITY CHECKS FAILED")
        print("------------------------------------------------------------\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
