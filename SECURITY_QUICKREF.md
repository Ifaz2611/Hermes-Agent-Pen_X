#  Quick Reference – Security & Encryption Features

## What Was Implemented

### 1. AES-256 Encrypted Data Vault ✅
- Protects API keys, sessions, config, and memories
- Password-based encryption with PBKDF2 key derivation
- 100,000 iterations for brute-force resistance
- Random salt per encryption for security

### 2. Hardware Token Support (Yubikey) ✅
- FIDO2/U2F passwordless authentication
- OTP and PIV certificate modes
- Optional PIN protection
- Falls back to password if key unavailable

---

## Essential Commands

### Encrypt Your Data
```bash
hermes security encrypt data/
```
Then set a strong master password. Files are encrypted automatically.

### Decrypt (Unlock)
```bash
hermes security decrypt data/
# Or just run launcher - it prompts automatically
./launch.bat
./launch.sh
```

### Check Status
```bash
hermes security status data/
python -m security token status
```

### Setup Yubikey
```bash
python -m security yubikey setup --mode fido2 --setup-pin
```

---

## File Locations

| What | Where |
|------|-------|
| Encryption module | `src/security/` |
| CLI tool | `src/security/cli.py` |
| Security guide | `SECURITY.md` |
| Implementation details | `IMPLEMENTATION_SUMMARY.md` |
| Windows unlock helper | `scripts/unlock-vault.ps1` |
| Unix unlock helper | `scripts/unlock-vault.sh` |

---

## What Gets Protected

Protected by default when encrypted:
- `.env` - API keys and secrets
- `config.yaml` - LLM configuration
- `soul.md` - Agent personality
- `sessions/` - Chat history
- `memory/` - Persistent memories
- `logs/` - Application logs

---

## How It Works

### On First Encryption
```
1. User runs: hermes security encrypt data/
2. System asks for master password
3. All sensitive files are encrypted with AES-256
4. Original files deleted, .enc files created
5. .vault config file marks vault as encrypted
```

### On Next Launch
```
1. Launcher detects encrypted vault (.vault file)
2. Prompts user for password
3. Decrypts data silently
4. Starts Hermes normally
```

### With Yubikey
```
1. Launcher detects Yubikey via USB
2. Uses FIDO2 for authentication (no password needed)
3. Falls back to password if Yubikey missing
```

---

## Quick Test

```bash
# Encrypt
hermes security encrypt data/

# Check status (should show encrypted: true)
hermes security status data/

# Decrypt
hermes security decrypt data/

# Check status again (should show encrypted: false)
hermes security status data/
```

---

## Security Guarantees

✅ **Industry Standard**: AES-256, PBKDF2 (NIST approved)
✅ **No Backdoors**: Open source, inspectable code
✅ **No Cloud**: Everything stays local on your device
✅ **Hardware Backed**: Yubikey resistant to phishing
✅ **Zero Knowledge**: Even developers can't recover lost passwords

---

## Installation

Already included in setup scripts:
- `setup-windows.ps1` - Installs cryptography & yubikey-manager
- `setup-unix.sh` - Installs cryptography & yubikey-manager

No extra steps needed!

---

## Get Help

- **Encryption questions**: See `SECURITY.md`
- **Technical details**: See `IMPLEMENTATION_SUMMARY.md`
- **Commands reference**: See `src/security/cli.py`
- **Troubleshooting**: See `SECURITY.md` Troubleshooting section

---

## Pro Tips

💡 Use strong passwords: `HeRm3s@P0rt@bl3#2024!`
💡 Setup Yubikey for convenience
💡 Backup encrypted data regularly
💡 Store password in password manager
💡 Keep on encrypted USB drive for portability

---

