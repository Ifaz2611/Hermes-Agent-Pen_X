"""profile_manager.py

Support for running multiple "clones" of Hermes with different SOUL.md profiles.
Profiles are stored in the data/profiles directory.
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


def get_portable_root() -> Path:
    env = os.environ.get('PORTABLE_ROOT')
    if env:
        return Path(env)
    # Fall back to the repo root derived from this file's location instead of
    # the current working directory (launchers may invoke us from anywhere).
    return Path(__file__).resolve().parents[2]


def get_data_dir() -> Path:
    return get_portable_root() / 'data'


def get_profiles_dir() -> Path:
    return get_data_dir() / 'profiles'


def validate_profile_name(name: str) -> str:
    """Validate and sanitize a profile name.

    Rejects absolute paths, traversal segments, path separators, reserved device names,
    and invalid characters before any file-system operation.
    """
    if not name or not isinstance(name, str) or not name.strip():
        raise ValueError("Profile name cannot be empty or whitespace.")

    name = name.strip()

    # Reject path separators
    if '/' in name or '\\' in name:
        raise ValueError(f"Invalid profile name {name!r}: path separators ('/' or '\\') are not allowed.")

    # Reject traversal segments
    if name in ('.', '..') or '..' in name:
        raise ValueError(f"Invalid profile name {name!r}: traversal segments are not allowed.")

    # Reject absolute paths (POSIX and Windows drive letters)
    if Path(name).is_absolute() or os.path.isabs(name) or (len(name) > 1 and name[1] == ':'):
        raise ValueError(f"Invalid profile name {name!r}: absolute paths are not allowed.")

    # Allowed character pattern: must begin with alphanumeric, contain only safe chars, no trailing dot
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', name) or name.endswith('.'):
        raise ValueError(
            f"Invalid profile name {name!r}: must start with an alphanumeric character and "
            "contain only letters, digits, underscores, dashes, and internal periods."
        )

    # Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{i}' for i in range(1, 10)} | {f'LPT{i}' for i in range(1, 10)}
    base_name = name.split('.')[0].upper()
    if base_name in reserved:
        raise ValueError(f"Invalid profile name {name!r}: reserved device name.")

    # Check that the resolved path stays strictly within the profiles directory
    profiles_dir = get_profiles_dir().resolve()
    target_path = (profiles_dir / name).resolve()
    if target_path.parent != profiles_dir:
        raise ValueError(f"Invalid profile name {name!r}: path escapes profiles directory.")

    return name


def list_profiles(as_json: bool = False):
    profiles_dir = get_profiles_dir()
    names = []
    if profiles_dir.exists():
        names = sorted([p.name for p in profiles_dir.iterdir() if p.is_dir()])
    if as_json:
        import json as _json
        print(_json.dumps([{"name": n, "path": str(profiles_dir / n)} for n in names]))
        return names
    if not profiles_dir.exists() or not names:
        print("No profiles found. Using default 'data' directory.")
        return names

    print(f"{'Profile Name':<20} {'Path':<40}")
    print("-" * 60)
    for name in names:
        print(f"{name:<20} {str(profiles_dir / name):<40}")
    return names


def create_profile(name: str) -> bool:
    name = validate_profile_name(name)
    profiles_dir = get_profiles_dir()
    profile_path = profiles_dir / name

    if profile_path.exists():
        print(f"Profile '{name}' already exists.", file=sys.stderr)
        return False

    profile_path.mkdir(parents=True, exist_ok=True)

    # Copy default files if they exist in data root.
    # soul.md is matched case-insensitively (SOUL.md on Windows, soul.md on Linux).
    data_dir = get_data_dir()
    files_to_copy = ['.env', 'config.yaml']
    soul_src = None
    for candidate in ('soul.md', 'SOUL.md', 'Soul.md'):
        if (data_dir / candidate).exists():
            soul_src = data_dir / candidate
            break

    for f in files_to_copy:
        src = data_dir / f
        if src.exists():
            shutil.copy2(src, profile_path / f)
            print(f"Copied {f} to profile '{name}'")
    if soul_src is not None:
        shutil.copy2(soul_src, profile_path / soul_src.name)
        print(f"Copied {soul_src.name} to profile '{name}'")
    else:
        # Create a basic soul.md if none exists
        with open(profile_path / 'soul.md', 'w', encoding='utf-8') as sf:
            sf.write(f"# {name} SOUL\n\nYou are a helpful AI assistant named {name}.\n")
        print(f"Created default soul.md for profile '{name}'")

    print(f"Profile '{name}' created at {profile_path}")
    return True


def delete_profile(name: str) -> bool:
    name = validate_profile_name(name)
    profiles_dir = get_profiles_dir()
    profile_path = profiles_dir / name

    if not profile_path.exists() or not profile_path.is_dir():
        print(f"Profile '{name}' does not exist.", file=sys.stderr)
        return False

    # Safety check: never delete profiles_dir or data_dir
    resolved_profile = profile_path.resolve()
    if resolved_profile == profiles_dir.resolve() or resolved_profile == get_data_dir().resolve():
        print(f"Cannot delete protected directory: {profile_path}", file=sys.stderr)
        return False

    shutil.rmtree(profile_path)
    print(f"Profile '{name}' deleted.")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hermes Profile Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List all profiles")
    list_parser.add_argument("--json", action="store_true",
                             help="Emit a JSON array of {name, path} objects")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new profile")
    create_parser.add_argument("name", help="Name of the profile")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a profile")
    delete_parser.add_argument("name", help="Name of the profile to delete")
    delete_parser.add_argument("--yes", action="store_true",
                               help="Required explicit confirmation flag for scripting")

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            list_profiles(as_json=getattr(args, "json", False))
            return 0
        elif args.command == "create":
            ok = create_profile(args.name)
            return 0 if ok else 1
        elif args.command == "delete":
            ok = delete_profile(args.name)
            return 0 if ok else 1
        else:
            parser.print_help()
            return 2
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
