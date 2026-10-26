# ADR-0004 — Self-contained Windows installer
Status: Accepted for M0 prototyping; distribution acceptance pending | Date: 2026-10-26

## Decision
Windows end users must not need Git, Python, pip, a terminal, or paid services. Package the native PySide6/QtWebEngine application as an onedir PyInstaller bundle on a Windows x64 CI runner. Wrap that folder in a per-user Inno Setup GUI installer with Start Menu shortcut, optional desktop shortcut and uninstall support.

The installed app's browser cookies/cache remain in the user's per-profile application data, outside the install directory, installer and repository. Uninstall does not silently wipe browser session data.

The build runs an automated *offline* load of about:blank in bundled Qt WebEngine to detect missing Chromium/Qt resources. It does not contact or authenticate with ChatGPT; site compatibility requires a separate, real Windows manual acceptance. No automations, APIs, agents or credential handling are permitted.

## Alternatives
- Telling end users to clone and pip-install: rejected as user-facing installation flow (allowed for contributors).
- Onefile PyInstaller build: deferred; onedir is more reliable for Qt WebEngine process/resources.
- Distribution through unreviewed or auto-published GitHub Release: rejected until sign-off.

## Risks / future work
CI-generated installer is unsigned. Windows SmartScreen may warn; do not teach users to disable security features. Pin tooling, calculate artifact hashes, add signing and release attestations in a later milestone, test live installation and uninstallation, and decide licensing before public release. Never claim an installer has been installed/tested on a user's Windows PC based only on GitHub CI.
