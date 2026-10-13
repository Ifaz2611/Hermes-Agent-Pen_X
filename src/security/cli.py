"""cli.py — ``python -m security`` command-line interface."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .crypto import DataVault
from .hardware_token import TokenManager, YubikeyManager


def _prompt_new_password() -> str:
    pw = getpass.getpass("Enter encryption password: ")
    confirm = getpass.getpass("Confirm password: ")
    if pw != confirm:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(2)
    if len(pw) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        raise SystemExit(2)
    return pw


def cmd_encrypt(args) -> int:
    vault = DataVault(args.path)
    if vault.is_encrypted():
        print(f"Vault already encrypted: {args.path}")
        return 0
    password = args.password or os.environ.get("HERMES_VAULT_PASSWORD") or _prompt_new_password()
    try:
        result = vault.lock(password)
    except ValueError as exc:
        print(f"Encryption failed: {exc}", file=sys.stderr)
        return 1
    print("Vault encrypted successfully!")
    print(f"  - Encrypted files: {result['encrypted_files']}")
    return 0


def cmd_decrypt(args) -> int:
    vault = DataVault(args.path)
    if not vault.is_encrypted():
        # Nothing to do — treat as success so launchers can proceed.
        return 0
    password = args.password or os.environ.get("HERMES_VAULT_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Enter vault password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nUnlock cancelled.", file=sys.stderr)
            return 1
    if not password:
        print("A password is required.", file=sys.stderr)
        return 1
    try:
        result = vault.unlock(password)
    except ValueError as exc:
        print(f"Failed to unlock vault: {exc}", file=sys.stderr)
        return 1
    print("Vault unlocked successfully!")
    print(f"  - Decrypted files: {result['decrypted_files']}")
    return 0


def cmd_recover(args) -> int:
    vault = DataVault(args.path)
    if not vault.has_pending_recovery():
        print(f"No interrupted operation to recover for vault: {args.path}")
        return 0
    try:
        result = vault.recover()
        print("Vault recovered successfully from interrupted operation!")
        print(f"  - Restored files: {result['recovered_files']}")
        return 0
    except Exception as exc:
        print(f"Recovery failed: {exc}", file=sys.stderr)
        return 1


def cmd_status(args) -> int:
    vault = DataVault(args.path)
    st = vault.get_vault_status()
    print(f"Vault Status ({args.path}):")
    print(f"  - Encrypted: {st['encrypted']}")
    print(f"  - Encrypted files: {st['encrypted_files']}")
    print(f"  - Total size: {st.get('total_size_human', st.get('total_size'))}")
    if st.get("pending_recovery"):
        print("  - Pending recovery: True (run 'python -m security recover')")
    return 0


def cmd_yubikey_setup(args) -> int:
    mgr = YubikeyManager(mode=args.mode)
    info = mgr.get_info()
    if not info.get("connected"):
        print("No Yubikey detected.")
        print(f"  Reason: {info.get('reason', 'unknown')}")
        print("  Install yubikey-manager and connect your key, then retry.")
        return 1
    print("Yubikey detected!")
    for key in ("device", "mode", "connected", "serial"):
        if key in info:
            print(f"  - {key}: {info[key]}")
    if args.setup_pin:
        res = mgr.setup_pin()
        print("PIN setup launched." if res.get("ok") else f"PIN setup issue: {res.get('reason')}")
    return 0


def cmd_token_status(args) -> int:
    mgr = TokenManager(token_type=args.type)
    st = mgr.status()
    print("Hardware token status:")
    for k, v in st.items():
        print(f"  - {k}: {v}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m security", description="Hermes data-vault security CLI")
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("encrypt", help="Encrypt the data vault")
    pe.add_argument("path", help="Vault directory (e.g. data/)")
    pe.add_argument("--password", help="Encryption password (prompts or uses HERMES_VAULT_PASSWORD if omitted)")
    pe.set_defaults(func=cmd_encrypt)

    pd = sub.add_parser("decrypt", help="Decrypt the data vault")
    pd.add_argument("path", help="Vault directory (e.g. data/)")
    pd.add_argument("--password", help="Vault password (prompts or uses HERMES_VAULT_PASSWORD if omitted)")
    pd.set_defaults(func=cmd_decrypt)

    pr = sub.add_parser("recover", help="Recover vault from an interrupted lock or unlock operation")
    pr.add_argument("path", help="Vault directory (e.g. data/)")
    pr.set_defaults(func=cmd_recover)

    ps = sub.add_parser("status", help="Show vault status")
    ps.add_argument("path", help="Vault directory (e.g. data/)")
    ps.set_defaults(func=cmd_status)

    py = sub.add_parser("yubikey", help="YubiKey device helpers (diagnostics only; not used for vault encryption)")
    ysub = py.add_subparsers(dest="yubikey_command", required=True)
    ys = ysub.add_parser("setup", help="Configure YubiKey PIN")
    ys.add_argument("--mode", default="fido2", choices=["otp", "fido2", "piv"])
    ys.add_argument("--setup-pin", action="store_true")
    ys.set_defaults(func=cmd_yubikey_setup)

    pt = sub.add_parser("token", help="Hardware token diagnostics (diagnostics only; not used for vault encryption)")
    tsub = pt.add_subparsers(dest="token_command", required=True)
    ts = tsub.add_parser("status", help="Check hardware token status")
    ts.add_argument("--type", default="auto", choices=["auto", "yubikey", "password"])
    ts.set_defaults(func=cmd_token_status)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
