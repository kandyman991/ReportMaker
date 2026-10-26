# Windows GUI installer — M0 preview

## User workflow — no developer tools
1. Open the [rolling Windows M0 GitHub prerelease](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0).
2. Under **Assets**, download `ReportMaker-M0-Setup.exe` and the optional `SHA256SUMS.txt` (direct assets; no GitHub Actions artifact ZIP).
3. If checking integrity, calculate the installer SHA-256 locally and compare it with the matching entry in `SHA256SUMS.txt`. Then run `ReportMaker-M0-Setup.exe`.
4. Choose the per-user installation; find ReportMaker in the Start Menu. A desktop shortcut is optional.
5. Try module scratchpad, manually copy/paste sample text, attempt ordinary website login only yourself, and test the external-browser fallback if the site rejects embedded login.
6. Remove with Windows **Installed apps** when finished.

This is a development preview. No actual customer database or Word generation exists yet. The installer is unsigned; Windows may show publisher/SmartScreen warnings. Only install builds you trust from this project's reviewed source; do not bypass corporate security controls.

## Build architecture
- Python 3.12 x64 on GitHub Actions Windows runner.
- Qt/PySide6 version pinned in pyproject; PyInstaller version pinned in packaging/windows/requirements-build.txt.
- PyInstaller **onedir** freezes the app and Qt WebEngine helper files to `dist/ReportMaker`.
- CI runs `ReportMaker.exe --self-test`: creates Qt WebEngine and loads `about:blank` without networking.
- Inno Setup creates **per-user** `ReportMaker-M0-Setup.exe`, bundled with all onedir application files and browser runtime; no Git/Python prerequisite on the target PC.
- After all build and offline smoke tests pass, CI updates a rolling **prerelease** tag `reportmaker-windows-m0`, replacing the installer and checksum assets in GitHub Releases. Do **not** publish as a production release.
- No `actions/upload-artifact` or Actions cache upload. A separate cleanup job runs after successful release publication and deletes only old ReportMaker installer Actions artifacts.
- The release has stable links but changes with each successful build; release notes identify the exact commit and build.
- The installer never embeds account credentials; user browser data is kept under Windows local application data.

## Limitations and requirements
- Windows 10/11 x64, Windows support to be verified by actual interactive acceptance.
- No signed publisher certificate yet; IT policy may block unsigned builds.
- The online ChatGPT website may reject embedded Chromium login. Do not bypass authentication/browser restrictions. Use the **Open ChatGPT in default browser** action.
- Website sessions depend on the site policies, not the installer. Uninstall leaves local profile/cache, which may include session cookies; deleting that profile should only be an explicit user action.
- No auto-updater. Do not run a new unreviewed build without checking its source/commit.
- The rolling M0 prerelease temporarily builds from the unmerged `feature/m0-windows-installer` branch; once merged, `main` is also an allowed publication branch. Treat all builds as test-only until reviewed and signed.

## Native Windows acceptance checklist
Follow `docs/M0_ACCEPTANCE.md` and `https://github.com/kandyman991/ReportMaker/issues/2`.
