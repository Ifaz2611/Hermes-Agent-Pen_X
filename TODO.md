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

- [x] **Make runtime downloads verifiable and reproducible.** Maintain
  versioned manifests and required checksums for each supported OS and
  architecture; fail setup clearly when verification fails.
- [x] **Add a diagnostics command for the portable wrapper.** Check supported
  platform, runtime versions, virtual environment, source checkout, data path,
  and optional dependencies without modifying user data.
- [x] **Improve upgrade and rollback handling.** Back up relevant metadata,
  explain changes before applying them, and provide a documented recovery path
  if an update fails.
- [x] **Add a backup/restore workflow.** Support selecting a destination,
  preserving relative paths, verifying restored files, and documenting
  encryption and password recovery limitations.
- [x] **Add CI checks for shell, PowerShell, Python, and JavaScript files.**
  Include Markdown-link validation and checks that generated files, runtime
  downloads, and local secrets are not accidentally tracked.
- [x] **Document supported versions and compatibility.** Keep the README,
  setup scripts, and command guide aligned with the actual runtime versions and
  launcher options.


## P3 — Optional features

- [x] **Add scheduled backup/sync support.** Make schedules opt-in, explain
  what data is uploaded, and provide a clear pause/disable control.
  (`tools/sync/schedule_manager.py`: `status`/`enable`/`pause`/`resume`/
  `disable`/`run-now --dry-run`/`check --run-if-due`; no schedule file means
  disabled; every preview lists source file count, bytes, encrypted count and
  destination; passphrases never stored.)
- [x] **Add backup retention and conflict handling.** Preview actions and
  protect existing remote data from silent overwrites.
  (`backup prune --keep N --dry-run`; `restore --dry-run` preview with
  `--overwrite-policy fail|skip|overwrite|keep-both` defaulting to `fail`;
  `s3_sync --no-overwrite`/`--conflict-policy` + `--verify` + `--retention-keep`
  with `--prune` required to delete.)
- [x] **Explore additional storage providers.** Consider other object-storage
  services only after S3 sync has reliable verification, errors, and recovery.
  (`tools/sync/providers.py`: `s3` default verified path, `s3-compatible`/
  `minio`/`wasabi`/`spaces`/`b2`/`r2` via `--endpoint-url` gated behind
  verification + `--dry-run` guidance, plus offline `local` provider for
  testing.)

