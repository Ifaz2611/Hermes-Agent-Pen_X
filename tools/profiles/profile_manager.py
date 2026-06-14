"""profile_manager.py

Support for running multiple "clones" of Hermes with different SOUL.md profiles.
Profiles are stored in the data/profiles directory.
"""

import argparse
import os
import shutil
from pathlib import Path

def get_portable_root():
    return Path(os.environ.get('PORTABLE_ROOT', Path.cwd()))

def get_data_dir():
    return get_portable_root() / 'data'

def get_profiles_dir():
    return get_data_dir() / 'profiles'

def list_profiles():
    profiles_dir = get_profiles_dir()
    if not profiles_dir.exists():
        print("No profiles found. Using default 'data' directory.")
        return

    print(f"{'Profile Name':<20} {'Path':<40}")
    print("-" * 60)
    for item in profiles_dir.iterdir():
        if item.is_dir():
            print(f"{item.name:<20} {str(item):<40}")

def create_profile(name):
    profiles_dir = get_profiles_dir()
    profile_path = profiles_dir / name
    
    if profile_path.exists():
        print(f"Profile '{name}' already exists.")
        return

    profile_path.mkdir(parents=True, exist_ok=True)
    
    # Copy default files if they exist in data root
    data_dir = get_data_dir()
    files_to_copy = ['.env', 'config.yaml', 'SOUL.md']
    
    for f in files_to_copy:
        src = data_dir / f
        if src.exists():
            shutil.copy2(src, profile_path / f)
            print(f"Copied {f} to profile '{name}'")
        else:
            # Create a basic SOUL.md if it doesn't exist
            if f == 'SOUL.md':
                with open(profile_path / f, 'w', encoding='utf-8') as sf:
                    sf.write(f"# {name} SOUL\n\nYou are a helpful AI assistant named {name}.\n")
                print(f"Created default SOUL.md for profile '{name}'")

    print(f"Profile '{name}' created at {profile_path}")

def delete_profile(name):
    profiles_dir = get_profiles_dir()
    profile_path = profiles_dir / name
    
    if not profile_path.exists():
        print(f"Profile '{name}' does not exist.")
        return

    shutil.rmtree(profile_path)
    print(f"Profile '{name}' deleted.")

def main():
    parser = argparse.ArgumentParser(description="Hermes Profile Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    subparsers.add_parser("list", help="List all profiles")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new profile")
    create_parser.add_argument("name", help="Name of the profile")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a profile")
    delete_parser.add_argument("name", help="Name of the profile to delete")

    args = parser.parse_args()

    if args.command == "list":
        list_profiles()
    elif args.command == "create":
        create_profile(args.name)
    elif args.command == "delete":
        delete_profile(args.name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
