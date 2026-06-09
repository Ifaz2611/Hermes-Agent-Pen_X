# Hermes Agent Pendrive_X – Zero-Install AI Agent Distribution

A fully self-contained, "zero-install" distribution of the Nous Research Hermes Agent. Run a complete AI agent environment from a USB drive without installing Python, Node.js, or any dependencies on your host machine.

## Key Features

- **Zero Host Pollution**: Everything stays inside the folder. No global environment variables or registry changes.
- **Independence**: Downloads and bundles its own runtimes (Python 3.11, Node.js 22, uv package manager).
- **Privacy by Default**: API keys, chat sessions, and memories stored locally in the `data/` directory.
- **Encryption Ready**: Built-in AES-256 encryption for sensitive files (API keys, sessions, config).
- **Hardware Token Support**: Optional Yubikey integration for secure, passwordless authentication.
- **Multi-Platform**: Works on Windows, macOS (Intel/Apple Silicon), and Linux (x86/ARM).
- **Interactive TUI**: Beautiful terminal-based dashboard for setup, chat, and management.

## Quick Start

### Windows

```bash
cd path\to\hermes-portable
.\launch.bat
```

### macOS / Linux

```bash
cd path/to/hermes-portable
bash launch.sh
# Or double-click launch.command on macOS Finder
```

The launcher will:
1. Download runtimes on first run (~600 MB)
2. Create an isolated virtual environment
3. Prompt you to unlock the vault (if encrypted)
4. Show an interactive dashboard

## Security & Encryption

Hermes now includes **enterprise-grade security** for your portable AI agent:

### Encrypted Data Vault (AES-256)

Protect your API keys, sessions, and configuration with military-grade encryption:

```bash
# Encrypt your data vault
hermes security encrypt data/

# Decrypt on next startup (you'll be prompted for password)
hermes security decrypt data/

# Check vault status
hermes security status data/
```

**Protected by default:**
- `.env` - API keys and secrets
- `config.yaml` - Configuration
- `sessions/` - Chat history
- `memory/` - Persistent memories
- `logs/` - Application logs

### Hardware Token Support (Yubikey)

Use a physical Yubikey for passwordless, phishing-resistant authentication:

```bash
# Setup Yubikey authentication
python -m security yubikey setup --mode fido2 --setup-pin

# Encrypt vault with hardware token support
hermes security encrypt data/ --hardware-token

# Check token status
python -m security token status
```

**Yubikey Benefits:**
- No password to remember or steal
- Hardware-backed cryptography
- Works even if vault password is compromised
- Supports multiple devices for backup

See [SECURITY.md](SECURITY.md) for complete encryption and Yubikey setup guide.

## Directory Structure

```
hermes-portable/
├── launch.bat              # Windows entry point
├── launch.sh               # macOS/Linux entry point
├── data/                   # Your identity (API keys, sessions, memory) ⭐
│   ├── .env               # API keys (encrypted by default)
│   ├── config.yaml        # Configuration
│   ├── soul.md            # Agent personality
│   ├── sessions/          # Chat history (encrypted)
│   └── memory/            # Persistent memories (encrypted)
├── src/                    # Hermes source code (cloned from GitHub)
│   └── hermes-agent/      # Official Hermes repository
├── .cache/                 # Downloaded binaries (Python, Node, uv, Playwright)
│   ├── runtimes/
│   │   └── windows-x64/   # Platform-specific runtimes
│   ├── logs/              # Launcher logs
│   └── npm/               # npm configuration
├── scripts/               # Setup, maintenance, vault unlock scripts
└── README.md, SECURITY.md, LICENSE

```

## Main Commands

### Chat Interface
```bash
./launch.bat                # Windows
./launch.sh                 # macOS/Linux
```

### Setup & Configuration
```bash
hermes setup                # Configure API provider and model
hermes config edit          # Edit configuration
hermes doctor               # Check environment
```

### Gateway (API Server)
```bash
hermes gateway              # Start API server
hermes gateway stop         # Stop API server
```

### Security & Encryption
```bash
hermes security encrypt data/              # Encrypt vault
hermes security decrypt data/              # Decrypt vault
hermes security status data/               # Check status
python -m security yubikey setup           # Configure Yubikey
```

### Advanced
```bash
hermes update               # Pull latest source
hermes --version            # Show version
hermes --help               # List all commands
```

## System Requirements

### Minimum
- **Storage**: 2 GB free space (for runtimes + data)
- **RAM**: 2 GB
- **Network**: Internet connection (first-run setup only)

### Recommended
- **Storage**: 5-10 GB (for chat history and offline models)
- **RAM**: 4-8 GB
- **USB Drive**: USB 3.0+ for better performance

### Supported Platforms
- Windows 10/11 (x64)
- macOS 10.15+ (Intel & Apple Silicon)
- Linux (x86_64, ARM64)

## 🔧 First-Time Setup Walkthrough

1. **Extract the portable folder** to your desired location (or USB drive)

2. **Run the launcher**
   - Windows: Double-click `launch.bat`
   - macOS: Run `bash launch.sh` or rename to `launch.command` and double-click
   - Linux: Run `bash launch.sh`

3. **Wait for first-run setup** (~3-5 minutes on first launch)
   - Downloads Python 3.11, Node.js 22, and other runtimes
   - Creates an isolated virtual environment
   - Installs Hermes and dependencies

4. **Configure your provider**
   - Choose your LLM provider (OpenAI, Anthropic, etc.)
   - Enter API key
   - Select default model

5. **(Optional) Encrypt your vault**
   - Run: `hermes security encrypt data/`
   - Set a strong master password
   - Next time you run Hermes, you'll be prompted to unlock

6. **Start chatting**
   - Select "Start Hermes Chat" from the dashboard
   - Interact with your AI agent

## Security Best Practices

1. **Encrypt the vault** if storing sensitive API keys
   ```bash
   hermes security encrypt data/
   ```

2. **Use strong passwords** (16+ characters with mixed case and symbols)

3. **Setup Yubikey** for passwordless authentication
   ```bash
   python -m security yubikey setup
   ```

4. **Backup your data**
   - Regular backups of `data/` folder (encrypted or not)
   - Store backups securely (encrypted cloud storage)

5. **Keep it updated**
   ```bash
   hermes update   # Pull latest Hermes version
   ```

## Troubleshooting

### First-run setup hangs or fails
- Check internet connection
- Try running setup with verbose output: `.\scripts\setup-windows.ps1 $PWD`
- Check logs: `.cache/runtimes/windows-x64/install.log`

### Vault unlock fails
- Ensure you're using the correct password (case-sensitive)
- Check `data/.vault` file exists
- Try decrypting manually: `hermes security decrypt data/`

### Yubikey not detected
- Check USB connection
- Try different USB port
- Run: `ykman list` to verify device detection
- Ensure ykman is installed: `pip install yubikey-manager`

### API errors
- Verify API key is correct in `.env` or via `hermes setup`
- Check your account has API access enabled
- Review API provider's rate limits and quotas

### Performance issues on USB drive
- Use USB 3.0+ drives (significant performance boost)
- Consider loading runtimes into RAM: Use `--ram-disk` flag (if supported)
- Run `hermes doctor` to check system health

For more help:
- See [SECURITY.md](SECURITY.md) for encryption questions
- Check [COMMANDS.md](scripts/COMMANDS.md) for all CLI options
- Review [Contributing.md](Contributing.md) for development

## Advanced Features

### Skills & Memory
- Create and manage agent skills
- Configure persistent memory systems
- Customize agent behavior via `soul.md`

### Multi-Agent Mode
- Run multiple instances with different configurations
- Each instance has its own `data/` folder
- Share or isolate memories and sessions

### Model Context Protocol (MCP)
- Built-in support for MCP servers
- Integrate tools and data sources
- Computer use capabilities via Playwright

### Telegram Integration
- Run Hermes as a Telegram bot
- Built-in webhook support for serverless deployment

## Documentation

- [SECURITY.md](SECURITY.md) - Complete encryption & Yubikey guide
- [COMMANDS.md](scripts/COMMANDS.md) - All CLI commands reference
- [Contributing.md](Contributing.md) - Development guide
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community guidelines

## Contributing

Contributions are welcome! Please see [Contributing.md](Contributing.md) for guidelines.

## License

See [license](license) file for details.

## Acknowledgments

Built with IMZ by the [Nous Research](https://nous-research.com) team.

---

**Pro Tip**: Store this portable folder on a **encrypted USB drive** for maximum security and portability!


                 |    |    |
                )_)  )_)  )_)
                )___))___))___)
               )____)____)_____)
             _____|____|____|_____
             \   SAIL  AWAY!    /
              \~~~~~~~~~~~~~~~~~/
       ~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~~^~^~
