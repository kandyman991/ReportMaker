# ReportMaker v0.5.0 — Windows release candidate and native acceptance

**Status:** Release candidate is a test build, not a production approval. User approved
replacing M0 as the current download after installed-Windows acceptance; keep M0
available as a historical rollback/fallback. This contract records the accepted
workflow; it does NOT claim tests have passed or that Windows is connected.

## Immutable tested source

- Canonical source: merged `main` at `1e092c175857bfd5969202201b2595604bb27b2f`.
- GitHub Actions frozen Windows x64 app built from this **exact commit**, never
  the release-preparation branch's executable sources.
- Build tooling may vary by GitHub Actions runner and is recorded in a single
  build/run; the published `ReportMaker-0.5.0-Setup.exe` and its SHA-256 are the
  acceptance unit. **Promote the exact same byte-identical installer**, with no
  new build, by copying the tested asset to a normal stable GitHub Release only
  after user confirms critical acceptance.
- Release candidate: `reportmaker-v0.5.0-rc.1` (GitHub prerelease), user-facing
  download link under its **Assets**; M0 historic tag
  `reportmaker-windows-m0` must not be moved, removed, overwritten or reclassified
  by this workflow. Never call the candidate a production release.
- Same Inno Setup AppId and install directory so this is a normal in-place
  per-user application upgrade, **not** a simultaneous second installation.
  Installer displays version 0.5.0 and a distinct distribution filename.
  No Python, Git or admin privileges needed on the user's Windows desktop.
- No Actions artifact upload, cache upload, production customer files, browsers'
  credentials, logs or private photos in GitHub releases.

## User's first installation

1. On the Windows PC, back up any previous local ReportMaker projects
   (`.rmproj`) and local SQLite/customer database and app settings to a
   **private local** folder. Close ReportMaker. Do not publish backup files.
2. From the GitHub release's official Assets, download both
   `ReportMaker-0.5.0-Setup.exe` and `SHA256SUMS.txt`.
   Verify the SHA-256 through PowerShell:
   `(Get-FileHash .\ReportMaker-0.5.0-Setup.exe -Algorithm SHA256).Hash`
   and compare with `SHA256SUMS.txt`.
3. Install normally on Windows 10/11 x64. The executable is unsigned; obey
   company IT policy and do not disable anti-malware/SmartScreen. Existing M0
   installation may be upgraded in place. The historical M0 download remains
   accessible as a fallback installer, but **old M0 cannot read new v2/v3 projects**.
4. Confirm Start menu launch, source/version identification, user-local DB/profile
   and project data preservation. Record Windows edition, x64, scaling,
   installed path, Word version and SHA-256. If installation fails, do not
   assert application acceptance.
5. Use **synthetic data/photos only**. Run the comprehensive
   [Windows acceptance checklist](WINDOWS_ACCEPTANCE_M0_M4.md) for M0–M4.
   Add M4.5.1/2 checks below. Share redacted result checkboxes/diagnostics,
   never login screenshots, original photos or customer databases.

## M4.5 native additional acceptance

- [ ] Import a locally created/synthetic JPEG/PNG and HEIC/HEIF, observe
  source vs optimized previews and dimensions. Confirm source-file checksum
  unchanged, no network requirement and working copy remains after source
  removed or moved.
- [ ] Validate media library, declared unused pictures, one picture inserted
  into two modules, and Save/Open portability. The original is external.
- [ ] Visual PhotoBlock editor: crop, rotate, flip, straighten, arrows/lines,
  rectangles/ellipses/highlights/freehand/text/callouts, move/delete shapes.
  Verify cancel vs apply, dialog Undo/Redo and report Undo/Redo.
- [ ] Save/reopen a v3 project. Verify same picture in two placements has
  independent annotations, no duplicate image bytes, and no lost markup.
- [ ] Open a synthetic v1/v2 project. Ordinary Save must refuse an in-place
  version change; Save As creates a separate v3 copy preserving the original.
- [ ] Export **unedited-photo** DOCX and PDF, visually inspect in actual
  Microsoft Word and a PDF viewer, verify page fields, module hierarchy,
  page breaks, captions, tables, branding, Italian accents, and Conclusions.
- [ ] Deliberately try DOCX/PDF export of a **visually edited** PhotoBlock.
  Until M4.5.4, a visible controlled error is **expected/pass**, not a
  production feature. Confirm no existing exported file is overwritten.
- [ ] Confirm ChatGPT is an ordinary browser panel, manual copy/paste only.
  The browser login may fail on embedded Qt; verify default-browser fallback,
  without providing account secrets to the acceptance report.

## Blocking release criteria

Production release **must not** occur before the user records acceptance of
critical M0–M4 and supported M4.5 functions on the **exact downloaded installer**
SHA. A critical crash, data loss, broken Save/Open/migration, database corruption,
missing HEIC codec, incorrect Word/PDF basic export, or installer failure blocks
promotion and requires a reviewed correction and new candidate hash.

Open product limitations, disclosed in release notes: unsigned Windows installer;
visually edited photographs cannot yet export to DOCX/PDF (M4.5.4 planned);
M4.5.3 private comments, M5 translations and M6 templates not implemented;
embedded chatgpt.com sign-in may be site-dependent; no automatic updater.

After acceptance: change the repository's current-download pointer to the
**stable** `v0.5.0` release, preserve M0 under its historical URL, and carry
over the identical installer + SHA256SUMS to stable without rebuilding. Do not
make an M0-only branch masquerade as the current release.

## Pending record

- RC GitHub Actions build: PENDING.
- RC release installer SHA-256: PENDING.
- Installed Windows: PENDING.
- Owner acceptance and production promotion: PENDING.
