# Contributing

Thanks for considering a contribution to Hermes Agent Pendrive_X. For significant changes, open or join a discussion with the repository maintainers before investing in implementation.

## Before you start

- Check existing issues and documentation to avoid duplicating work.
- Keep changes focused and compatible with the repository’s Windows and macOS/Linux targets.
- Do not include API keys, passwords, personal data, generated runtime downloads, or local user data.
- Read and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development workflow

1. Create a focused branch from the project’s current default branch.
2. Make the smallest complete change and update directly related documentation.
3. Run relevant checks for the affected platform and scripts. For launcher/setup changes, check argument forwarding and fresh setup paths; for security changes, test against disposable data.
4. Open a pull request describing the problem, the change, platform coverage, and validation performed. Include screenshots for user-facing UI changes when useful.

Do not claim a test or platform check was run unless it was actually run. If a platform is unavailable, state that clearly in the pull request.

## Pull requests

- Keep pull requests focused and explain any user-visible behavior changes.
- Document new flags, environment variables, file locations, or dependencies in the appropriate guide.
- Preserve portability and avoid relying on the caller’s current working directory.
- Never commit secrets, generated virtual environments, downloaded runtimes, or user data.
- Maintainers will determine review requirements and release/versioning details.

## Security issues

Do not report exploitable vulnerabilities in a public issue. Use the private reporting channel described in [`SECURITY.md`](SECURITY.md).
