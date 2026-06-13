UX & Management additions

1) Electron GUI launcher (gui/electron)
  - Minimal Electron app (index.html, main.js) providing:
    * Launch Hermes (runs launch.bat)
    * Open Health Dashboard (attempts to run doctor command)
    * Open data/ folder in file explorer
  - To run:
      cd gui/electron
      npm install
      npm start

2) S3 Sync (tools/sync/s3_sync.py)
  - Uploads files from data/ to S3. When --encrypt is used, files are encrypted with
    the repository's EncryptionManager and uploaded as .enc JSON files.
  - Example:
      python tools\sync\s3_sync.py --bucket my-bucket --prefix hermes-backup --encrypt --password "my-pass"
  - Requires: boto3 (pip install boto3)

3) Health Dashboard
  - The GUI currently triggers the existing TUI doctor via the "Open Health Dashboard" button.
  - Recommendation: add a small API or JSON exporter for hermes doctor so the Electron app can present a graphical dashboard (future).

Security notes
- The sync script uses passphrase-based encryption derived with PBKDF2 and Fernet (already present in src/security/crypto.py).
- Do not commit passphrases or AWS credentials to the repo. Use environment variables or AWS profiles.

Next steps (optional)
- Implement JSON export endpoint for hermes doctor (to feed the Electron dashboard).
- Add automatic scheduled sync and conflict resolution UI.
