# Hermes Agent Pendrive_X - Security & Encryption Guide

## Overview

Hermes Agent Pendrive_X now includes built-in encryption for your data vault and optional hardware token support via Yubikeys. This guide covers all security features and how to use them.

## Features

### 1. AES-256 Encrypted Data Vault

**What it does:**
- Encrypts all sensitive files in your `data/` folder (API keys, sessions, config)
- Uses AES-256 encryption with PBKDF2 key derivation
- Protects against data theft if your USB drive is lost or stolen

**Benefits:**
- **Privacy**: API keys and session data remain encrypted at rest
- **Portability**: Safely carry sensitive data on USB drives
- **Zero-Knowledge**: Only you have the encryption password
- **Standards-Based**: Uses industry-standard cryptography (Python `cryptography` library)

### 2. Yubikey & Hardware Token Support

**What it does:**
- Integrates with Yubikey devices for passwordless authentication
- Supports multiple authentication modes: FIDO2, OTP, PIV
- Can serve as a second factor for vault unlocking

**Benefits:**
- **Convenience**: No password to remember
- **Security**: Hardware-backed keys resistant to phishing and malware
- **Portability**: Same physical key for your portable agent
- **Flexibility**: Fall back to password if key not available

## Installation

### Basic Installation

The security module is included by default. Install the required dependencies:

```bash
# For encryption support (required)
pip install cryptography>=41.0.0

# For Yubikey support (optional but recommended)
pip install yubikey-manager>=5.0.0
```

Or use the setup script which includes these by default:

```bash
# Windows
.\setup-windows.ps1

# macOS/Linux
./setup-unix.sh
```

## Quick Start

### Encrypt Your Data Vault

```bash
# Using the launcher (recommended)
hermes security encrypt data/

# Or manually via CLI
python -m security encrypt data/
```

You'll be prompted to enter a master password (minimum 8 characters).

### Decrypt Your Data Vault

When you next start Hermes after encryption, it will automatically prompt you:

```
🔐 Hermes Agent vault detected.
Enter encryption password: ••••••••
✓ Vault unlocked successfully!
```

Or decrypt manually:

```bash
python -m security decrypt data/
```

### Check Vault Status

```bash
hermes security status data/

# Output:
# Vault Status (data/):
#   - Encrypted: true
#   - Encrypted files: 12
#   - Total size: 2.45 MB
#   - Hardware token enabled: false
```

## Yubikey Setup

### Prerequisites

1. **Physical Yubikey device** (Yubikey 4/5/5C/5Ci or compatible)
2. **ykman installed** (included in setup):
   ```bash
   pip install yubikey-manager
   ```

### Setup Yubikey for Authentication

#### Step 1: Enable FIDO2 on Yubikey

```bash
python -m security yubikey setup --mode fido2 --setup-pin
```

This will:
- Detect your connected Yubikey
- Display device information
- Optionally set up a PIN for additional security

#### Step 2: Enable Hardware Token in Launcher

When encrypting your vault, use the `--hardware-token` flag:

```bash
hermes security encrypt data/ --hardware-token
```

This configures the launcher to:
- Check for a connected Yubikey on startup
- Use Yubikey for vault authentication (if available)
- Fall back to password if Yubikey not connected

#### Step 3: Test Authentication

```bash
python -m security token status --type yubikey

# Output:
# Token Status (yubikey):
#   - token_type: yubikey
#   - device_info:
#       device: Yubikey
#       mode: fido2
#       connected: true
#       serial: XXXXXXXX
#       firmware_version: 5.2.7
#   - is_available: true
```

## Usage Examples

### Example 1: Basic Encryption (Password Only)

```bash
# Encrypt vault
$ hermes security encrypt data/
Encrypting vault at: data/
Enter encryption password: ••••••••
Confirm password: ••••••••

✓ Vault encrypted successfully!
  - Encrypted files: 8
  - Total size: 1.23 MB
```

Then when you run Hermes, it will automatically ask for the password:

```bash
$ ./launch.bat
🔐 Hermes Agent vault detected.
Enter encryption password: ••••••••
✓ Vault unlocked successfully!

Loading Hermes Chat...
```

### Example 2: Hardware Token + Password (Recommended)

```bash
# Setup Yubikey
$ python -m security yubikey setup --mode fido2 --setup-pin
✓ Yubikey detected!
  - device: Yubikey
  - mode: fido2
  - connected: true
  - serial: 12345678
  - firmware_version: 5.2.7

# Encrypt with hardware token support
$ hermes security encrypt data/ --hardware-token
Encrypting vault at: data/
Enter encryption password: ••••••••
Confirm password: ••••••••

✓ Vault encrypted successfully!
  - Encrypted files: 8
  - Total size: 1.23 MB
  - Hardware token enabled: true
```

Now on startup, Hermes will:
1. Check for connected Yubikey
2. If found: Use Yubikey for authentication (just touch the key)
3. If not found: Fall back to password prompt

### Example 3: Decrypt Vault for Backup

```bash
$ python -m security decrypt data/
Decrypting vault at: data/
Enter encryption password: ••••••••

✓ Vault decrypted successfully!
  - Encrypted files: 8
  - Total size: 1.23 MB
```

All `.env`, sessions, and configs are now in plaintext. You can:
- Back up the decrypted files
- Transfer to another machine
- Re-encrypt when done

## Technical Details

### Encryption Algorithm

- **Cipher**: Fernet (symmetric encryption)
- **Key Derivation**: PBKDF2 with SHA-256
- **Iterations**: 100,000
- **Salt**: 16 random bytes per encryption
- **Key Length**: 256 bits (32 bytes)

### Files Protected by Default

The following files are encrypted:
- `.env` - API keys and secrets
- `config.yaml` - Configuration
- `soul.md` - Agent personality
- `gateway.pid` - Process information

The following directories are encrypted recursively:
- `sessions/` - Chat history
- `memory/` - Persistent memories
- `logs/` - Gateway and application logs

### Storage Format

Encrypted files are stored as JSON with:

```json
{
  "ciphertext": "gAAAAABlMz...",
  "salt": "rnd3xyz..."
}
```

Original file is replaced with `.enc` extension (e.g., `.env.enc`).

### Vault Configuration

A `.vault` file in the data directory tracks encryption status:

```json
{
  "encrypted": true,
  "use_hardware_token": false,
  "version": "1.0"
}
```

## Security Considerations

### Password Best Practices

1. **Use a strong password** (16+ characters recommended)
   - Mix uppercase, lowercase, numbers, and symbols
   - Avoid dictionary words and personal information
   - Example: `HeRm3s@P0rt@bl3#2024!`

2. **Never share your password**
   - Not even with Nous Research support
   - Hermes developers cannot recover encrypted data

3. **Remember or backup your password**
   - Lost password = lost data
   - Consider using a password manager

### Yubikey Best Practices

1. **Use a PIN on your Yubikey** (set during setup)
   - Protects key from casual physical access
   - Recommended PIN: 4-8 random digits

2. **Register multiple Yubikeys** (if available)
   - Provides backup if one is lost
   - Same authentication works on all registered keys

3. **Keep your Yubikey safe**
   - Treat it like a physical door key
   - Don't lose it or leave it unattended

4. **Document your Yubikey serial**
   - Write it down and store safely
   - Helps identify your key if multiple are registered

### Data Recovery

If you forget your password:

1. **With Yubikey backup**: Use the Yubikey to access the vault
   ```bash
   python -m security decrypt data/ --hardware-token
   ```

2. **Without backup**: You'll need to:
   - Delete the encrypted `.enc` files
   - Restore from a backup (if available)
   - Note: There is no password recovery

## Troubleshooting

### "Failed to unlock vault (incorrect password?)"

- Check that password is entered correctly (case-sensitive)
- Try copying password from password manager if available
- If using Yubikey, ensure it's connected and charged

### "No Yubikey detected"

- Check USB connection (try different USB port)
- Run: `ykman list` to verify detection
- Restart Hermes launcher
- Try Yubikey Manager GUI to verify device works

### "Permission denied" when encrypting/decrypting

- Check that `data/` directory is not read-only
- On Unix: `chmod -R 755 data/`
- On Windows: Right-click folder → Properties → Security

### "Module not found" errors

Reinstall dependencies:

```bash
# Windows
.\setup-windows.ps1 -Root %CD%

# Unix
./setup-unix.sh
```

Or manually:
```bash
pip install cryptography>=41.0.0 yubikey-manager>=5.0.0
```

## Advanced Configuration

### Disable Hardware Token Requirement

If your Yubikey is lost but you know the password:

```bash
# Decrypt with password only
python -m security decrypt data/

# Encrypt without hardware token requirement
python -m security encrypt data/
```

### Rotate Encryption Password

1. Decrypt vault:
   ```bash
   python -m security decrypt data/
   ```

2. Re-encrypt with new password:
   ```bash
   python -m security encrypt data/
   ```

### Export Encrypted Files

All encrypted files use standard JSON format and can be:
- Backed up to cloud storage (still encrypted)
- Transferred between machines
- Inspected for audit purposes

```bash
# Backup encrypted vault
cp -r data/*.enc backup/

# Restore from backup
cp backup/*.enc data/
```

## Reporting Security Issues

If you discover a security vulnerability, **please do not** file a public GitHub issue.

Instead:
1. Email: security@nous-research.com (replace with actual security contact)
2. Include: Affected component, reproduction steps, potential impact
3. Allow 48 hours for acknowledgment

## Additional Resources

- [Cryptography Library Documentation](https://cryptography.io/)
- [Yubikey Documentation](https://docs.yubico.com/)
- [OWASP Password Guidelines](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [FIDO2 Security](https://fidoalliance.org/)

## Support

For issues or questions:
1. Check this guide's Troubleshooting section
2. Review vault status: `hermes security status data/`
3. Check logs: `hermes doctor`
4. Contact support with error messages and logs

---


