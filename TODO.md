# Roadmap and Future Work

This list tracks possible improvements for Hermes Agent Pendrive_X. Items are
proposals, not promises or descriptions of completed functionality. Priorities
indicate suggested order: **P1** reliability and security, **P2** usability,
**P3** optional expansion.

## P1 — Reliability and security

- [x] **Add automated tests for the security module.** Cover encrypt/decrypt
  round trips, wrong passwords, already-encrypted files, mixed vault contents,
  and failures without changing the original data.
- [x] **Make vault updates recoverable.** Write encrypted/decrypted file
  contents atomically, preserve recoverable backups during an operation, and
  test behavior when the process stops partway through.
- [x] **Resolve the YubiKey integration gap.** Either design and implement a
  reviewed, genuinely key-backed vault factor with recovery procedures, or
  remove the hardware-token metadata/options that might imply it protects the
  vault. Do not advertise passwordless vault unlocking until it is implemented
  and tested.
- [x] **Harden profile names and paths.** Reject absolute paths, traversal
  segments, and invalid names before creating or deleting profile data.
- [x] **Add cross-platform smoke tests.** Exercise launcher argument
  forwarding, setup dry runs, vault unlocking, and reset previews on Windows,
  macOS, and Linux.
- [x] **Improve S3 sync failure reporting.** Ensure dry-run can show planned
  uploads without requiring AWS access, report individual failures, and return
  a non-zero exit status if any upload fails.
- [x] **Review secret handling in tools.** Avoid requiring passwords in command
  arguments where possible, document credential sources, and test that logs
  never include secret values.

## P2 — Setup and maintenance

- [ ] **Make runtime downloads verifiable and reproducible.** Maintain
  versioned manifests and required checksums for each supported OS and
  architecture; fail setup clearly when verification fails.
- [ ] **Add a diagnostics command for the portable wrapper.** Check supported
  platform, runtime versions, virtual environment, source checkout, data path,
  and optional dependencies without modifying user data.
- [ ] **Improve upgrade and rollback handling.** Back up relevant metadata,
  explain changes before applying them, and provide a documented recovery path
  if an update fails.
- [ ] **Add a backup/restore workflow.** Support selecting a destination,
  preserving relative paths, verifying restored files, and documenting
  encryption and password recovery limitations.
- [ ] **Add CI checks for shell, PowerShell, Python, and JavaScript files.**
  Include Markdown-link validation and checks that generated files, runtime
  downloads, and local secrets are not accidentally tracked.
- [ ] **Document supported versions and compatibility.** Keep the README,
  setup scripts, and command guide aligned with the actual runtime versions and
  launcher options.

## P2 — User experience

- [ ] **Make the Electron dashboard report actionable health checks.** Show
  missing runtimes, setup state, vault state, and useful log excerpts with
  clear error messages.
- [ ] **Expose safe profile management in the UI.** List, create, and switch
  profiles while requiring explicit confirmation before deleting one.
- [ ] **Add accessible UI states.** Support keyboard navigation, visible focus,
  readable error messages, and high-contrast themes.
- [ ] **Improve first-run progress and cancellation.** Report download/setup
  stages, preserve logs, and leave the next launch in a recoverable state after
  cancellation.

## P3 — Optional features

- [ ] **Add scheduled backup/sync support.** Make schedules opt-in, explain
  what data is uploaded, and provide a clear pause/disable control.
- [ ] **Add backup retention and conflict handling.** Preview actions and
  protect existing remote data from silent overwrites.
- [ ] **Explore additional storage providers.** Consider other object-storage
  services only after S3 sync has reliable verification, errors, and recovery.
- [ ] **Provide release packaging.** Produce versioned archives with checksums,
  a changelog, supported-platform notes, and a clean install/upgrade guide.
