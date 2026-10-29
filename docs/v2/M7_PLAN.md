# M7 — Checkpoint D acceptance and release plan

**Started:** 2026-10-29, after merged M6.7 PR #89.  
**Base:** post-merge `main` `b875c4f6a6f68552decf740d5eab7f506318e1db` (includes merge `6cd9565a1514e84c1ee2a21543174dafef4c911e`).  
**Status:** In development. M7.1 isolated draft PR; **no V2 release, V1 replacement, or native installed-PC acceptance yet**.  
**Tracking:** [M7 parent issue #90](https://github.com/kandyman991/ReportMaker/issues/90), [M7.1 issue #91](https://github.com/kandyman991/ReportMaker/issues/91), [33-feature matrix](M7_ACCEPTANCE_MATRIX.json).

## Sequential, independently reviewed boundaries

| Slice | Scope | Acceptance and merge boundary |
| --- | --- | --- |
| **M7.1 — Frozen V2/isolated installer preflight** | Dedicated V2 launcher, different per-user installation identity, Windows-hosted build/freeze/silent install/offline smoke/uninstall, static release-boundary tests and feature register | All CI jobs green, independent review; **not** physical Windows UI or release authorization |
| **M7.2 — Legacy project and migration acceptance** | Synthetic v1–v4 and v5 Save As, master snapshot, original file preservation, translations, assets, older V1 fallback behavior | Malformed/unsupported versions fail closed; no destructive overwrite; canonical IDs and source data verified |
| **M7.3 — Installed Windows interaction / 33 features** | Branch editing, native keyboard/focus, wheel/touchpad, display scaling, 33 RM-BE requirements, native Explorer drop and clipboard, long/deep reports | Per-case redacted evidence on real installed x64 Windows; fixes plus rechecks |
| **M7.4 — Complex Word and PDF fidelity** | DOCX/DOTX import support/warnings, multilingual fonts/typography, template logos/footers, page refs, narrow tables/long documents, PDF comparison | Native Word visual/field evidence with exact approved fixtures; unsupported features explicitly documented |
| **M7.5 — Manual ChatGPT browser compatibility and privacy** | Embedded website login, normal text/image copy/download, external fallback, user intent, browser storage isolation; track issue #64 | Real user-controlled website/manual test; no automation, browser data export or credential capture |
| **M7.6 — Reviewed Windows release candidate and Checkpoint D** | Reinstall/update/uninstall, integrity and rollback, release checklist, independent full review, V1 preserved | **Separate explicit user approval** before publishing V2 installer or default promotion |

## M7.1 engineering contract

M6 already has real canonical session, multilingual exports and synthetic acceptance. But the existing released Windows installers freeze the **legacy V1** launcher, not `reportmaker.v2`. Thus a newly installed V2 candidate must be created independently before physical UI acceptance can begin.

- `packaging/windows/v2_launcher.py` launches `reportmaker.v2`, never the old `reportmaker.__main__`.
- `packaging/windows/ReportMaker-V2-M7.iss` uses a **distinct AppId, installation folder, Start Menu/desktop labels and executable**. It cannot overwrite the existing per-user V1 install. The M0/RC2/RC3 workflows are left unchanged.
- `.github/workflows/v2-m7-packaging.yml` is a **read-only-permissions Windows CI preflight**: compile, source V2 offline smoke, M6.7 integration regression, PyInstaller V2 freeze, frozen offline smoke, install the resulting installer into a temporary per-user path, check installed-executable hash, run installed offline smoke, uninstall. No browser login, customer data or production media.
- **No release upload or Actions binary artifacts.** The candidate installer built in CI is ephemeral. This milestone is NOT proof that GUI, DPI, keyboard, clipboard, browser login or Word are correct on the user's installed computer.

## 33-feature acceptance evidence rules

The machine-readable [M7 acceptance register](M7_ACCEPTANCE_MATRIX.json) lists **exactly the 33 RM-BE-001 IDs** in their specification order, with explicit manual scenarios. Every case begins `pending_native_acceptance` even when it already has Linux/offscreen or hosted Windows coverage. A case may be marked passed only after a separately reviewed change supplies:

1. A specific tested V2 source and installer checksum, Windows edition/build, display DPI/scaling, installed app version, relevant Word version/fonts when applicable (do not publish host/user identity).
2. The synthetic test steps, expected versus observed result and any issue/PR for a failure. Capture only sanitized screenshots/summary; never upload real customer reports, ChatGPT conversations, cookies, tokens or screenshots with private content.
3. A durable evidence reference, reviewer, and date for each accepted case. Failure blocks Checkpoint D; skipped tests are not passes.

Focus native checks on the known risks: [browser copy/download #64](https://github.com/kandyman991/ReportMaker/issues/64), [complex DOCX letterhead #45](https://github.com/kandyman991/ReportMaker/issues/45), Gallery Explorer/clipboard and DPI editing, Word/PDF pagination and backward-compatible Save As. CI cannot log into the user's ChatGPT account or operate a licensed Word installation on their behalf.

## Restrictions

The binding `AGENTS.md`, root `ARCHITECTURE.md`, and [V2 architecture](ARCHITECTURE.md) remain unchanged. No second report model or browser bridge; no public customer assets. Existing V1 releases remain fallback. A successful M7.1 CI does **not** accept M7.3–M7.6, publish a V2 release, or approve promotion to default.
