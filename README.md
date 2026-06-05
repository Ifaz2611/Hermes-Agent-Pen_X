# <p align="center">🛸 Hermes Agent — Portable & Cross-Platform</p>

<p align="center">
  <img src="https://img.shields.io/badge/Hermes_Agent-Portable-8A2BE2?style=for-the-badge&logo=ai" alt="Hermes Agent Portable">
  <img src="https://img.shields.io/github/license/NousResearch/hermes-agent?style=for-the-badge&color=2563EB" alt="License">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-059669?style=for-the-badge" alt="Platforms">
</p>

---

<p align="center">
  <strong>Run a fully self-contained, self-improving AI agent from a single folder or USB drive.</strong><br>
  No global installation. Zero host pollution. All conversations, configs, memories, and skills stay inside your folder.
</p>

<p align="center">
  <a href="https://youtu.be/gL220WHXWeo" target="_blank">
    <img src="https://img.youtube.com/vi/gL220WHXWeo/maxresdefault.jpg" alt="Hermes Portable Setup Walkthrough Video" width="700" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.15);">
  </a>
  <br>
  <em>📺 <strong>Watch the Setup & Demo Video:</strong> Click the image above to watch the step-by-step walkthrough.</em>
</p>

---

## ✨ Key Features

*    **Zero Host Dependencies**: No pre-installed Python, Node.js, or package managers required on the computer. All runtimes are downloaded locally.
*    **100% Portable**: Copy the entire directory to a USB flash drive or external SSD. Run it on any Windows, macOS, or Linux computer instantly.
*    **True Privacy & Isolation**: Your API keys (`data/.env`), conversations (`data/sessions/`), persistent memory, and custom skills are kept strictly within the portable folder.
*    **Interactive Console Launcher**: Includes a beautiful terminal UI dashboard with state-tracking for setup status, LLM providers, and background gateways.
*    **Full Hermes Capabilities**: Retains all features of [Nous Research's Hermes Agent](https://github.com/NousResearch/hermes-agent), including memory storage and reusable skill generation.

---

## ⚡ Quick Start

Get Hermes running in seconds depending on your operating system:

### Windows (10 / 11)
Simply double-click the **`launch.bat`** file in this folder.
> *Note: On first run, it will launch a PowerShell window to download dependencies and configure your runtime environment.*

###  macOS & Linux
Open your terminal in this directory and execute:
```bash
chmod +x launch.sh
./launch.sh
```

> 💡 **macOS Double-Click Shortcut:** If you want to double-click in Finder to launch, rename `launch.sh` to `launch.command`. macOS recognizes `.command` files and opens them in Terminal automatically.

---

## ⚙️ How It Works (Under the Hood)

Hermes Portable solves the host-dependency issue by establishing a sandboxed runtime context pointing inwards.

```mermaid
graph TD
    A[User triggers launch script] --> B{Runtimes setup?}
    B -- No / First Run --> C[Download Portable Python 3.11 & Node.js 22]
    C --> D[Clone Hermes Agent Source to src/]
    D --> E[Create isolated virtual env using uv]
    E --> F[Install Python & Node packages locally]
    F --> G[Generate ready.flag]
    B -- Yes / Ready --> H[Configure environment variables]
    G --> H
    H --> I[Set HERMES_HOME = data/]
    I --> J[Prepend portable bin/ paths to Env PATH]
    J --> K[Launch Terminal Dashboard Menu]
    K --> L[Start Chat / Background Gateway]
```

### The Isolation Design
1. **Custom Data Directory**: The launcher overrides `HERMES_HOME` to the local `data/` folder, forcing Hermes to write configuration and data locally rather than in `~/.hermes/`.
2. **Local Path Sandboxing**: The scripts download self-contained Python and Node.js binaries into `.cache/runtimes/` and prepend them directly to the active process `PATH`.
3. **No Registry/Host Pollution**: System configurations, environment variables, or packages on the host machine are left untouched.

---

## 📁 Workspace Directory Structure

A clean, modular layout where runtime caches are separated from your personal configurations.

```yaml
hermes-portable/
├── launch.bat                 # Windows interactive launcher script
├── launch.sh                  # macOS & Linux interactive launcher script
├── scripts/
│   ├── setup-windows.ps1      # Windows first-run configuration script
│   └── setup-unix.sh          # Unix (macOS/Linux) first-run configuration script
├── data/                      # ⚠️ [BACKUP THIS] All your private files
│   ├── config.yaml            # Hermes LLM provider configurations
│   ├── .env                   # API Keys and active credentials
│   ├── sessions/              # Chronological chat histories
│   ├── memories/              # Persistent memory databases
│   └── skills/                # Learned custom skills
├── src/                       # Downloaded Hermes Agent source code
│   └── hermes-agent/
└── .cache/                    # Sandbox cache & binaries
    └── runtimes/              # Platform-specific portable interpreters
        ├── windows-x64/
        ├── macos-arm64/
        ├── macos-x64/
        ├── linux-x64/
        └── linux-arm64/
```

---

## 🗝️ Setup API Keys

To configure your language models, open and edit the environment variables in `data/.env`:

```env
# Add the keys for the providers you wish to use:
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

Alternatively, you can select option **`[2]` (Setup / Reconfigure)** in the Launcher Terminal Menu to configure model providers interactively.

---

## 🖥️ Supported Platforms

| Operating System | CPU Architecture | Setup Status | Notes |
| :--- | :--- | :--- | :--- |
| **Windows 10 / 11** | x86_64 | ✅ Supported | Default Powershell ExecutionPolicy bypassed for script |
| **macOS 13+** | Apple Silicon (ARM64) | ✅ Supported | Native M1/M2/M3 execution |
| **macOS 13+** | Intel (x86_64) | ✅ Supported | Legacy Intel Mac support |
| **Linux (Ubuntu/Arch/Debian)** | x86_64 | ✅ Supported | Fully self-contained |
| **Linux (Fedora/CentOS)** | ARM64 | ✅ Supported | Supports SBCs and ARM Servers |

---

## 📦 Cache & Runtime Footprint

| Component | Storage Size | Notes |
| :--- | :--- | :--- |
| **Launchers & Scripts** | ~50 KB | Metadata and setup automation scripts |
| **Per-Platform Runtime** | ~600 – 900 MB | Includes Python, Node, uv, and pip caches |
| **Hermes Source Code** | ~50 MB | Cloned Git repository |
| **User Data** | ~10 MB → 2 GB+ | Grows as memory and chat history expand |

> ℹ️ *Note: If you run this folder across multiple operating systems (e.g., Windows at home and macOS at work), the `.cache/runtimes/` folder will scale to store the respective platforms (~1.8 GB total).*

---

## 🔄 Updating Hermes Agent

Keep your agent up-to-date with the latest improvements from Nous Research:

*   **Via Chat Command**: Within an active Hermes conversation, type:
    ```text
    /hermes update
    ```
*   **Via Launcher**: Navigate to `[4] Advanced Options` -> `[5] Update Hermes` in the Launcher terminal dashboard.
*   **Manual Rebuild**: Delete `.cache/runtimes/<your-platform>` and the `src/hermes-agent` directory, then re-run the launcher to fetch the latest code from scratch.

---

## 🔒 Security Advisory

> [!WARNING]
> **Your portable directory contains your identity.**
> Because `data/.env` stores raw API keys and `data/sessions/` contains logs of your conversations, anyone with access to your portable drive can access your accounts.
> 
> *   **Recommended Action**: Encrypt your USB flash drive or SSD using **BitLocker** (Windows), **FileVault** (macOS), or a cross-platform utility like **VeraCrypt**.
> *   Avoid storing large API balances or production keys on drives you carry daily.

---

## 🔍 Troubleshooting & FAQ

<details>
<summary><strong> First-run setup fails or times out</strong></summary>

*   Verify your internet connection (the setup downloads ~600 MB of data).
*   Some corporate/school firewall settings block Node.js CDNs or GitHub releases. Try configuring a VPN.
*   Delete the `.cache/` folder and launch again to clean-install the runtimes.
</details>

<details>
<summary><strong> macOS: "cannot be opened because the developer cannot be verified"</strong></summary>

*   Right-click `launch.sh` (or `launch.command`), choose **Open With** and select **Terminal**.
*   Alternatively, open terminal and strip macOS quarantine flags using:
    ```bash
    xattr -dr com.apple.quarantine /path/to/hermes-portable
    ```
</details>

<details>
<summary><strong> Windows Defender flags the launcher scripts</strong></summary>

*   This is a false positive caused by PowerShell scripts downloading files from remote sources (GitHub & Node.js servers).
*   Click **"More info"** on the Windows SmartScreen dialog, then click **"Run anyway"**.
*   The setup scripts are fully open-source and human-readable under the `scripts/` directory for your inspection.
</details>

<details>
<summary><strong> Hermes is running slowly from my flash drive</strong></summary>

*   Older USB 2.0 drives have slow read/write speeds, which bottleneck Python's modules import.
*   **Solution**: Upgrade to a **USB 3.0 / 3.1** drive, or an **external SSD** for optimal performance.
</details>

<details>
<summary><strong> Playwright / Web Browser tools are failing</strong></summary>

*   Some OS sandboxing policies restrict web browsers (Chromium/Firefox) from starting directly inside external/removable directories.
*   **Solution**: Copy the `hermes-portable` directory onto the local SSD and run from there.
</details>

---

## 📝 Credits & Attribution

*   **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** — Powerful Agentic core created by [Nous Research](https://github.com/NousResearch).
*   **[python-build-standalone](https://github.com/indygreg/python-build-standalone)** — Portable Python interpreter compilation.
*   **[uv](https://github.com/astral-sh/uv)** — Blazing fast package installer and resolver.
