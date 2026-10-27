# Windows RC2: pinned build and installed acceptance

Status: **RC2 build configuration**, not stable/production approval.
Repository: kandyman991/ReportMaker.
Source snapshot: `9865178a0ccdfe27e79fc16640c0c3eca50fe099`
(the exact `main` head immediately after merging PRs #22 and #25 and
its generated handoff snapshot). This is the code used to create the installer;
merging the packaging PR does not silently change the application source.

## Build and publication contract

- Separate `.github/workflows/windows-rc2.yml`, leaving the
  historical M0-only `.github/workflows/windows-installer.yml` unchanged.
- The initial workflow-file merge automatically triggered the RC2 build on
  `main` as run [40518468145](https://github.com/kandyman991/ReportMaker/actions/runs/40518468145).
  Subsequent maintenance changes do **not** rebuild or overwrite a published
  immutable RC2 tag: only a deliberate manual workflow_dispatch from main.
  No release job on pull requests, forks or non-main branches.
- Check out **both** the current `main` configuration and the immutable pinned
  source, and verify the source SHA and that no application/legacy packaging
  files changed between them. Every RC2 run refers to the same source SHA.
- Install `.[desktop]` plus pinned PyInstaller; compile and run all synthetic
  Python regressions, freeze PySide6/QtWebEngine/reportmaker/pillow-heif.
- Run the **frozen executable itself** with `--self-test`,
  `--layout-self-test`, `--customer-self-test`,
  `--visual-editor-self-test` and `--export-self-test`.
  No browser sign-in, live customer data or external report/template is used.
- Build `ReportMaker-0.5.0-rc.2-Setup.exe` with
  `packaging/windows/ReportMaker-RC2.iss` using the same per-user AppId;
  create `SHA256SUMS.txt`, verify local SHA-256 and both remote asset sizes.
- Create a **draft** GitHub release, upload both artifacts, and make it public
  only when all gates pass, under a dedicated immutable
  `reportmaker-v0.5.0-rc.2` tag. Never overwrite RC1/M0 or an existing RC2
  tag. Any failed build must not publish an installer.
- The setup executable is **unsigned**. Its Windows install, working WebEngine,
  Word/PDF fidelity and test of the user's original DOCX example require
  native user acceptance; hosted runners cannot certify that outcome.

Prerelease: https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-v0.5.0-rc.2
Build history: https://github.com/kandyman991/ReportMaker/actions/workflows/windows-rc2.yml

## User's native Windows acceptance

1. Verify `SHA256SUMS.txt` matches the downloaded setup file using
   PowerShell `(Get-FileHash .\ReportMaker-0.5.0-rc.2-Setup.exe -Algorithm SHA256).Hash`.
2. Install the new version, launch and inspect normal/dark Windows themes,
   DPI scaling, resizable panes and embedded browser with external fallback.
3. Create/reopen a project; test database and manual customers, editing,
   Undo/Redo, modules, nested summary, photos, HEIC conversion, annotations,
   rich font and paragraph controls and direct page editing.
4. Import the private `Report_inglese.docx` **locally only** as a page template;
   inspect letterhead/header/footer/logo, margins, text style and disclose
   unsupported complex Word art or tables (the adapter is deliberately partial).
5. Export DOCX and PDF; check real installed fonts, numbering, borders,
   accurate page contents and layout in desktop Word and a PDF viewer.
6. Report bugs and repro steps. Keep RC2 prerelease until critical native
   Windows acceptance passes; do not promote to production automatically.

The active Word template is an **application-wide preference**, not stored in
the .rmproj file: verify the selected customer letterhead before each export.
The editable page is not an exact Word pagination clone. Customer documents,
original photographs and browser profiles must never be uploaded to GitHub.

## Initial RC2 evidence / draft inspection correction

- Initial automatic Windows build run **40518468145**: pinned source verification,
  full synthetic suite, PyInstaller freeze, all five frozen-executable probes,
  Inno compilation and local SHA-256 verification **PASSED**. Its final publish
  step **FAILED** because it called GitHub's public release-by-tag REST endpoint
  for a **draft**, which returns HTTP 404; the draft and two uploaded assets
  were intact. The workflow run stays red as audit history (not a build failure).
- Verified the uploaded draft through authenticated `gh release view`:
  `ReportMaker-0.5.0-rc.2-Setup.exe` (165381076 bytes) and
  `SHA256SUMS.txt` (100 bytes). Downloaded the manifest and checked it exactly
  matched the SHA-256 from the Windows run:
  `2365407baaf793b45988eb562fc57e96abcd87c39f62138993ff1f5a7f19a822`.
  The existing draft was then promoted to a public RC2 **prerelease**, no
  replacement build or overwrite needed.
- Follow-up code corrects the draft inspection to use authenticated
  `gh release view ... --json assets,isDraft,isPrerelease` and verifies public
  release status the same way. The one-time automatic push trigger is removed
  now that RC2 exists, preventing a new red build when this fix merges.
- Native installed-Windows/real DOCX/Word/PDF acceptance remains deferred until
  the user tests the RC2 asset. This release is not stable production.
