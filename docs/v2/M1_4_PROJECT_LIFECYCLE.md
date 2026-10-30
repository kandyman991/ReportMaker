# M1.4 — Project Lifecycle and Checkpoint A

**Status:** feature implementation submitted for independent review; no installer or merge authorized.
**Base main:** `bdf41cf9095368b297ccde9276e6ac89ff6221d3` (after merged M1.3 PR #69).
**Branch:** `feature/v2-m1-4-project-lifecycle`.
**Contract:** `docs/v2/M1_IMPLEMENTATION_PLAN.md`, `ARCHITECTURE.md`, `docs/v2/ARCHITECTURE.md`.

## Implemented workflow

- V2 Branch Editor remains the only primary workspace. A Qt project toolbar provides **New**, **Open**, **Save**, and **Save As**. Shortcuts: Ctrl+N, Ctrl+O, Ctrl+S and Ctrl+Shift+S.
- **New** requests a nonblank one-off manual customer name and constructs a new report with a fresh root, an editable first module, an obligatory dedicated Conclusions section, today as start/end date, and an English initial source language. It does not automatically create a database customer. Full report metadata forms are deferred to M6; no other metadata is dropped from saved projects.
- **Open** validates the detached untrusted archive with the existing v1–v4 loader, then atomically replaces the canonical session. A cancelled picker, bad file or unsaved-changes refusal leaves the active report, undo history and view identity unchanged.
- **Save** and **Save As** call the M1.2 `ProjectPersistence` adapter and v4 atomic serializer. The first Save chooses a destination. Explicit overwrite confirmation is required for an existing first-Save/Save-As target. v1–v3 sources route Save to Save As at a different path; original bytes stay unchanged.
- Pending inline drafts block unrelated operations. Save/Save As explicitly ask **Apply and save / Discard edits / Cancel**; New/Open/Close ask **Apply edits / Discard edits / Cancel** before the existing committed-unsaved-changes prompt. Cancel is the default and retains drafts/identity; approved Apply is atomic and one Undo step across editors; approved Discard clears only staged work. No implicit apply. See `docs/adr/0009-save-applies-pending-edits.md`.
- The local Qt presentation store keeps only selected module ID and scroll offset, keyed by SHA-256 of stable report ID and normalized project path. First Save and Save As rekey this state **only after** successful archive write and retain the previous identity; failed/cancelled paths do not change settings. Module selection is checked against the reopened canonical hierarchy. This state is not added to `.rmproj` or exported reports. Expanded state, focus, zoom and other M2/M5 presentation tools are not implemented early.
- Changing project generation drops stale title-caret/selection restoration requests. V1 GUI, browser/ChatGPT, and existing project schema are unchanged.

## Automated evidence / limits

- `tests/test_v2_lifecycle.py` covers synthetic New, manual customer, toolbar wiring, model/Qt edits, nested content, Unicode, undo/redo, initial Save, Save As, reopen, local settings migration, failed Save As, existing-file refusal, blocked drafts, closing, invalid archive, unsaved prompts, legacy v3 upgrade, and a printed measured 83-node initial UI render. It uses only a temporary local directory and Qt offscreen.
- `.github/workflows/v2-lifecycle.yml` runs Python 3.11 + 3.12 on hosted Windows with real PySide6, M1.4 tests and M1.3/M1.2 compatibility, plus the V2 launcher import firewall. Existing M0/V1 workflows are also expected to pass.
- **Not yet established:** a physically installed Windows build, real mouse/keyboard/DPI observation, user's approved sketch fidelity, a release-ready installer, arbitrary-size perf scaling, or full 33-requirement completion. Hosted Windows runner is not installed-PC acceptance.

## Manual Windows Checkpoint A checklist

Use the exact reviewed PR/release commit on a real Windows x64 PC and record device, Windows version, Qt version, screen resolution and DPI 100%, 125%, and 150%.

1. Launch V2 and verify one connected branch (root → module → submodule → paragraph → final Conclusions), not the old three-panel tree.
2. New: type a one-off customer name, create a module/submodule/paragraph, apply multiline Unicode edits, and verify caret/selection and connector alignment after resize and scroll.
3. Save to a fresh `.rmproj`, reopen, inspect exact module IDs/order and content; edit, undo, redo, Save As elsewhere, and reopen each copy.
4. Cancel New/Open/Save, try both choices for unsaved change prompt, leave multiple inline drafts and attempt Save/Open/Close; there must be no data loss or forced discard.
5. Open old valid v1–v3 project and ensure Save directs to a different path; verify original archive unchanged. Reject corrupted or future-version files without replacing the active report.
6. Confirm first Save/Save As local view selection restoration and failure rollback; check keyboard shortcuts, file pickers, native fonts, 100/125/150% scaling, responsive redraw and no focus theft.
7. Validate V1 still launches; do **not** treat legacy browser image copying, media, rich toolbar, drag/drop, virtualized layouts or M2–M6 features as M1.4 acceptance.

**Gate:** user visual approval and installed-Windows evidence are outstanding. Do not describe Checkpoint A as fully accepted merely because CI passes. Review this PR and all final-head checks before requesting an authorized merge.
