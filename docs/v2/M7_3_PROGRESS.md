# M7.3 — Physical installed-Windows Branch Editor acceptance

**Status: STARTED / 0 of 33 physical RM-BE cases accepted.** Work tracked in [issue #96](https://github.com/kandyman991/ReportMaker/issues/96), parent [#90](https://github.com/kandyman991/ReportMaker/issues/90).
**Baseline:** M7.2 merged PR #95 (`1774cedb18ac53b60a04d298268f31c227655d19`); mechanical `main` tip `f3e9e5e661f49ba5d3bacef6202d866aa3bdc621`.
**Source of truth:** [33-case matrix](M7_ACCEPTANCE_MATRIX.json). Its statuses stay `pending_native_acceptance` until separately reviewed, reproducible, sanitized real-Windows evidence has been accepted. Neither synthetic tests nor hosted Windows Actions prove physical native UI behavior.

## Boundaries

- This development slice adds **local build and local evidence tools**, not a release or 33 passed checks. The connected development device is Linux and cannot run physical installed-Windows UI checks.
- Preserve V1's executable, installer AppId and installation directory. The new build script reuses the **distinct V2 preview** Inno recipe; no GitHub Release, V1 update, or V2-default promotion. A user-requested one-day **unsigned manual QA workflow artifact** is permitted solely for M7.3 physical testing; ordinary PR validation still uploads no binary.
- Report modules/editor/export use the same canonical report. Browser remains user-controlled; no OpenAI API, browser automation, scraping, cookie/profile copying or unattended transfer.
- A full M7.3 review/merge requires explicit user authorization; M7.4 native Word, M7.5 live browser and M7.6 release/promotion remain independent.

## Physical x64 Windows procedure (not hosted CI)

1. On the **physical Windows PC to be tested**, install Python 3.12 x64, Git and Inno Setup 6 through trusted official installers. Fetch the approved PR commit, verify `git rev-parse HEAD`, and ensure tracked files are clean. Run from PowerShell at the repository root:

   ```powershell
   powershell -NoProfile -File .\scripts\build_v2_m73_local.ps1 -Install
   ```

   This explicitly opted-in local step creates a **new isolated** `ReportMakerV2.exe` installation (default `%LOCALAPPDATA%\ReportMaker-M73-PhysicalAcceptance`) and a local-only preview setup (default `%LOCALAPPDATA%\ReportMaker-M73-LocalPreview`). It checks exact source SHA, frozen/source offline smoke, every frozen-versus-installed payload file, and installed offline smoke. It refuses an already existing target. It never modifies the V1 installer or publishes binaries. Source and SHA-256 values appear in `m73-local-build.json`. If real Windows installation fails, log a blocker and **do not** claim native acceptance.

2. Start the installed V2 GUI interactively, use **only synthetic data**, and note Windows edition/build plus every test monitor's DPI/display scaling. Execute at least normal 100% and a different physical scale (e.g. 125% or 150%) for cases where resizing/focus, image handling and DPI apply. Vary mouse, keyboard, wheel/touchpad and Explorer clipboard as the scenario specifies. Do not mark passed based on offscreen screenshot testing.

3. Create a private dossier **outside the Git checkout**, then list all manual scenarios:

   ```powershell
   $py = ".\.venv\Scripts\python.exe"
   $private = Join-Path $env:LOCALAPPDATA "ReportMaker-M73-PrivateEvidence"
   $setup = Join-Path $env:LOCALAPPDATA "ReportMaker-M73-LocalPreview\ReportMaker-V2-M7-Preview-Setup.exe"
   $app = Join-Path $env:LOCALAPPDATA "ReportMaker-M73-PhysicalAcceptance\ReportMakerV2.exe"
   $buildManifest = Join-Path $env:LOCALAPPDATA "ReportMaker-M73-LocalPreview\m73-local-build.json"
   $sha = (git rev-parse HEAD).Trim()
   & $py scripts\m73_native_acceptance.py prepare --output $private --installer $setup --installed-exe $app --build-manifest $buildManifest --source-sha $sha --display-scale "100%, 150% tested" --tester-alias "Tester-1"
   & $py scripts\m73_native_acceptance.py list --dossier $private
   ```

4. Perform each scenario from the matrix and its linked RM-BE-001 specification. For every manual **pass**, save a **redacted** synthetic-only PNG/JPEG screenshot under `$private\evidence\BE-L01.png` (case-specific name); for a failure/block, file or link a GitHub issue with synthetic reproduction, expected versus observed, while excluding personal files or profile information. An example **record**, not an actual result:

   ```powershell
   & $py scripts\m73_native_acceptance.py record --dossier $private --case BE-L01 --result pass --steps "Created and edited a nested synthetic report in Modules" --observed "Content edited directly in place" --evidence BE-L01.png
   ```

   For `fail` or `blocked`, include `--issue https://github.com/kandyman991/ReportMaker/issues/NUMBER` instead of inventing a passing screenshot. Never mark skipped/untested as pass. After fixing a failure, install a new candidate and rerun the affected and regression cases; do not mix two source/installer SHAs in one dossier.

5. Have a **different human reviewer** inspect each synthetic scenario and its redacted evidence, including observed behavior and integrity. They separately record the review:

   ```powershell
   & $py scripts\m73_native_acceptance.py review --dossier $private --case BE-L01 --decision accept --reviewer-alias "Reviewer-2" --notes "Physical Windows action and redacted proof independently checked"
   & $py scripts\m73_native_acceptance.py summary --dossier $private
   ```

   The local summary says `complete: true` only at 33/33 independently accepted **on the single exact build**. It does not modify the checked-in matrix or automatically upload screenshots. Before any externally shared review summary, **manually inspect its text for private information**. Case evidence is still private and its SHA-256 is recorded for reviewer integrity; do not add raw screenshots, browsing sessions or machine/user identity to public GitHub.

## Acceptance buckets

The canonical matrix has **6 layout**, **7 editing**, **7 structural**, **7 usability**, and **6 integration** requirements, all 33 separately tracked. Prioritize the high-risk manual interactions: Unicode long-content caret/selection and DPI (BE-L04/E01/U05); drag Before/After/Inside and subtree IDs (BE-S01/S02); clipboard bitmap/file lists and Explorer drop (BE-U06/U07); cross-tab draft conflict (BE-I01); canonical TOC/Conclusions (BE-I02); local Gallery/asset ownership (BE-E03/E04/I04). Some cases necessarily overlap later M7.4 Word evidence (BE-I05) and M7.5 **manual** browser compatibility (BE-I04/I06); keep them unaccepted until their actual native checks have happened.

## Preparation verification

- Nine acceptance-tool unit tests exercise 33 pending cases, separate review, non-destructive ledger updates, evidence hash changes, failure issue requirements, source/installer/installed EXE build-manifest consistency, future approved matrix-status changes without breaking older dossiers, local Windows builder boundaries, and refusal to treat Linux as real Windows.
- Windows build script and native GUI steps **must still be tested on a physical Windows x64 PC**. A successful local synthetic/unit/hosted-CI run is preparation only.
- Source, hash, OS build and scale evidence are recorded without hostname, Windows username, browser cookies or customer content; ensure redaction/cropping is done **before** storing any screenshot. Do not publish screenshots automatically.

**Next gate:** A physical Windows owner must perform these tests and supply a privacy-reviewed status/evidence reference for each case. Independently review failures, implement fixes in the M7.3 PR, rerun targeted native regressions, and only then consider M7.3 acceptance/merge. Remain on V1 as the supported fallback until separately authorized M7.6.

## Initial review hardening
- Acceptance files bind to the SHA-256 of the stable **ordered scenario IDs and manual acceptance descriptions**, rather than the mutable matrix status/evidence fields. Otherwise an approved matrix-status change would make its underlying native dossiers unreadable.
- The local builder treats untracked source files as a dirty worktree and writes PyInstaller's `.spec` outside the repository, so exact SHA refers to the code being packaged and repeat runs do not create untracked build specs.
- Hosted M7.1 preflight additionally parses the M7.3 PowerShell build script **without executing it**, protecting CI from syntax regressions without pretending to install it on a physical PC.

## User-requested prebuilt installer for physical Windows testing

The V2 M7.1 workflow now supports an **explicitly opted-in manual M7.3 QA installer artifact**, without changing the behavior of ordinary PR CI. The temporary ZIP contains only `ReportMaker-V2-M7-Preview-Setup.exe` and `M73-QA-CHECKSUMS.txt`. The artifact expires after **one day** and can be downloaded by users with access to the repository Actions run; because this is a public repository, treat this artifact as publicly accessible during its brief lifetime. This is an **unsigned test build**, not an official release, and is not evidence of physical GUI acceptance.

The requested build is dispatched for the exact approved M7.3 PR head from GitHub Actions using the manual `manual_qa_installer=true` input, after source/frozen/installed smoke and full payload-hash validation. On your Windows PC:
1. Open the successful workflow-run URL provided for the **exact source SHA**, scroll to **Artifacts**, and download the `ReportMaker-V2-M73-TEST-ONLY-...` ZIP.
2. Extract it and inspect `M73-QA-CHECKSUMS.txt`. Use PowerShell to compare the extracted setup to its listed SHA-256:
   ```powershell
   Get-FileHash -Algorithm SHA256 ".\ReportMaker-V2-M7-Preview-Setup.exe"
   ```
   **Stop if the hashes do not match.** Do not disable Windows security protections.
3. After verifying the test build is the expected one, launch the setup manually. It installs `ReportMaker V2 Preview` independently in the per-user `%LOCALAPPDATA%\Programs\ReportMaker V2 Preview` directory; existing V1 remains separate. Do not use real customer reports, account credentials or private media during the acceptance session.
4. Record the installed V2 executable's checksum separately (the workflow manifest contains the installer hash). No claim of an automatically linked native-dossier `build-manifest` is made for a prebuilt setup; native evidence tracking on the physical Windows PC still requires the separate manual dossier and review process.

If the download has expired, request a new manual QA workflow run; do not use a random third-party mirror. No installer is attached to an ordinary PR check and no release is published.

## First physical Windows feedback — native blocker #98 (2026-10-29)

The Windows user confirmed the unsigned GitHub Actions QA installer (run 40911125858, exact source SHA `9315a93ddce28277bb7c0ea7a1d6d5ab5ebec94a`, verified setup hash `48a305aa4a3869a3803592446475c64f9112490f0d387f8efbf8bb187ecaa8c1`) **installs and launches successfully**. This is an initial physical smoke observation only; no native RM-BE scenario is accepted yet.

The first BE-L01 attempt: the user built a nested synthetic module and edited/styled text in Modules, but subsequent attempts to add modules/submodules/paragraphs/photos, drag and Save appeared to fail. Save displayed the **Unapplied edits** modal; per-card Apply/Revert buttons were almost unreadable in the supplied screenshot. The source command/draft architecture deliberately rejects structural changes while inline drafts are pending to protect the user's words. The user has been instructed to manually Apply each edited card and retry; independent insert/drag faults are **not ruled out** until that retest.

Issue [#98](https://github.com/kandyman991/ReportMaker/issues/98) tracks this blocker. Current correction on draft PR #97 adds a high-contrast yellow recovery panel with **Apply all edits** (one atomic, explicit canonical batch/Undo step) or **Discard edits…** (separate Yes/No confirmation), makes per-card Apply/Revert legible under Windows themes, and directs Save and blocked toolbar operations to the controls. It never auto-commits drafts or crosses the Editor draft owner's boundary. Offscreen Qt regression covers edit → blocked insertion → intentional Apply → insertion → Save/reopen, multi-edit atomic Undo, explicit cancel/revert, cross-editor ownership and rejected-batch rollback. **Do not mark BE-L01 complete** until the corrected installer is installed and rerun on the physical Windows PC, including a new screenshot and verified Save/reopen.
