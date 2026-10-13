"""mcp_manager.py

Simplified interface to manage Model Context Protocol (MCP) servers in the portable environment.
Manages mcp_config.json in the HERMES_HOME directory.
"""

import argparse
import json
import os
import sys
from pathlib import Path

def get_hermes_home():
    env = os.environ.get('HERMES_HOME')
    if env:
        return Path(env)
    # Derive the repo root from this file's location (tools/mcp/ -> root),
    # not the CWD, so direct invocations still target <root>/data.
    return Path(__file__).resolve().parents[2] / 'data'

def get_mcp_config_path():
    return get_hermes_home() / 'mcp_config.json'

def load_config():
    config_path = get_mcp_config_path()
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {"mcpServers": {}}
    return {"mcpServers": {}}

def save_config(config):
    config_path = get_mcp_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def list_servers():
    config = load_config()
    servers = config.get("mcpServers", {})
    if not servers:
        print("No MCP servers configured.")
    else:
        print(f"{'Server Name':<20} {'Command':<40}")
        print("-" * 60)
        for name, info in servers.items():
            command = " ".join(info.get("command", [])) if isinstance(info.get("command"), list) else info.get("command", "N/A")
            print(f"{name:<20} {command:<40}")

def add_server(name, command, args=None, env=None):
    if not name or not command:
        print("Server name and command are required.", file=sys.stderr)
        raise SystemExit(2)
    config = load_config()
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    if name in config["mcpServers"]:
        print(f"Server '{name}' already exists. Use 'remove' first to replace it.", file=sys.stderr)
        raise SystemExit(1)

    server_config = {
        "command": command,
        "args": args or []
    }
    if env:
        server_config["env"] = env

    config["mcpServers"][name] = server_config
    save_config(config)
    print(f"Added MCP server: {name}")

def remove_server(name):
    config = load_config()
    if "mcpServers" in config and name in config["mcpServers"]:
        del config["mcpServers"][name]
        save_config(config)
        print(f"Removed MCP server: {name}")
    else:
        print(f"Server '{name}' not found.", file=sys.stderr)
        raise SystemExit(1)

AVAILABLE_SERVERS = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    },
    "google-maps": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-google-maps"]
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"]
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"]
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"]
    }
}

def list_available():
    print(f"{'Available Server':<20} {'Description':<40}")
    print("-" * 60)
    descriptions = {
        "filesystem": "Read/write access to the local file system",
        "google-maps": "Search places and get directions",
        "brave-search": "Web search via Brave API",
        "postgres": "Read/write access to PostgreSQL databases",
        "github": "Interact with GitHub repositories"
    }
    for name in AVAILABLE_SERVERS:
        print(f"{name:<20} {descriptions.get(name, 'N/A'):<40}")

def install_server(name):
    if name in AVAILABLE_SERVERS:
        server = AVAILABLE_SERVERS[name]
        try:
            add_server(name, server["command"], server["args"])
        except SystemExit as e:
            if e.code == 1:
                print(f"Server '{name}' is already installed.")
                return
            raise
        print(f"Successfully installed {name}!")
    else:
        print(f"Server '{name}' not found in available list. Use 'add' for custom servers.", file=sys.stderr)
        raise SystemExit(1)

def main():
    parser = argparse.ArgumentParser(description="Hermes MCP Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    subparsers.add_parser("list", help="List configured MCP servers")

    # Available command
    subparsers.add_parser("available", help="List available MCP servers to install")

    # Install command
    install_parser = subparsers.add_parser("install", help="Install a pre-defined MCP server")
    install_parser.add_argument("name", help="Name of the server to install")

    # Add command
    # NOTE: --args uses REMAINDER so dash-prefixed values (e.g. -y) work
    # without a '--' separator. It must therefore be the LAST option given.
    add_parser = subparsers.add_parser("add", help="Add a new custom MCP server")
    add_parser.add_argument("name", help="Name of the server")
    add_parser.add_argument("--cmd", required=True, help="Command to run the server")
    add_parser.add_argument("--env", nargs="*", metavar="KEY=VALUE",
                            help="Environment variables for the server (e.g. --env API_KEY=xyz)")
    import argparse as _argparse
    add_parser.add_argument("--args", nargs=_argparse.REMAINDER,
                            help="Arguments for the command (LAST option, e.g. --args -y pkg)")

    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove an MCP server")
    remove_parser.add_argument("name", help="Name of the server to remove")

    args = parser.parse_args()

    if args.command == "list":
        list_servers()
    elif args.command == "available":
        list_available()
    elif args.command == "install":
        install_server(args.name)
    elif args.command == "add":
        env = {}
        for item in (args.env or []):
            if "=" not in item:
                print(f"Ignoring malformed --env entry (want KEY=VALUE): {item}", file=sys.stderr)
                continue
            key, value = item.split("=", 1)
            env[key] = value
        cmd_args = list(args.args or [])
        if cmd_args and cmd_args[0] == "--":
            cmd_args = cmd_args[1:]
        add_server(args.name, args.cmd, cmd_args, env or None)
    elif args.command == "remove":
        remove_server(args.name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
