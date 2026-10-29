# M6.7 — End-to-end integration and Checkpoint C

**Status:** In development on isolated draft branch
`feature/v2-m6-7-checkpoint-c`, based on post-M6.6 `main`
`e2a44f78ade51cf5879481c23b7377bb57770195`.
This is the **final M6 implementation/review boundary**, not a V2
installer/release, V1 replacement or automatic merge authorization.
Track planned acceptance in [M6 submilestones](M6_SUBMILESTONES.md),
[roadmap](ROADMAP.md), and GitHub issue #87.

## Locked integration invariants

- Preserve the **one** canonical report/session and stable IDs across
  Modules, Editor, Gallery, Preview, and manual-only ChatGPT tab.
  Contents/TOC is always derived from the canonical report hierarchy.
- No hidden browser automation, report-to-ChatGPT transfer, imported
  customer files or external network dependency. The offscreen Qt test
  explicitly avoids activating WebEngine.
- Source content, translations and v5 metadata approvals have one
  validated command history, with one-step compound editing undo/redo.
  Pending drafts fail closed for save, export and project switching.
- Project photos retain approved project-owned bytes and placement-only
  annotations. The export renderer is explicit. PDF and DOCX remain
  distinct with documented native Word fidelity constraints.
- Legacy v1–v4 project Save As, V1 fallback, frozen customer identity,
  presentation-only state and atomic export are retained; no new format
  version and no unrelated redesign.

## M6.7-A — Integrated synthetic user-path gate

Added `tests/test_v2_m67_checkpoint.py` using the actual V2 main window,
Qt offscreen, canonical command gateway and actual persistence/export.
It exercises one fabricated report across:

1. Gallery import of an extra synthetic PNG, with original placed
   image bytes unchanged and no duplicate report hierarchy.
2. Canonical Report Information update with a manual frozen
   customer/site/machine snapshot, multiple intervention types,
   intervention dates/ticket/personnel and selected languages.
3. Two simultaneous document-Editor drafts (nested paragraph and
   table cell), with Save/PDF/ZIP rejection until one atomic Apply.
   Undo/Redo returns the exact prior/approved report, including IDs.
   A **direct Branch Editor title edit** is then applied, and the
   Page Editor scope selector and Contents both reflect it.
4. Report-owned photo rotation/shape/text marks, then explicit
   canonical command approvals of content and metadata translations.
   Generated Contents and every workspace use the same session/IDs;
   embedded ChatGPT browser is not loaded.
5. Save as portable v5 `.rmproj`, compare report/media library and
   assets to the validated archive, and reopen through real main-window
   lifecycle. Generation changes; report IDs, derived TOC, immutable
   pictures and approved translations survive.
6. Actual source-language editable DOCX/PDF export; translated
   language-specific Word export; PDF proof; all-language DOCX/PDF ZIP.
   Validate editable OOXML structure, body text, independent PDF,
   manifest and internal archive members. Source report stays unchanged.
7. A late source edit stales translation; existing translated DOCX
   and ZIP remain byte-for-byte unchanged after failed exports.
   Undo restores the full approved report.
8. A corrupt project fails to replace the current open report;
   missing translations cannot replace an existing archive. No
   partial temp archives or private browser assets are saved.

## M6.7-B — Unapplied edit visibility

Window title's existing unsaved marker was only recalculated on
**canonical** changes, not the first draft or last Revert. Connected
a pure boolean pending-state notification in `DraftCoordinator` to the
V2 main window caption. No parallel model, no disclosure of draft text,
no synchronous widget teardown and no modification to command validation.
The integrated Qt test verifies that both page Editor and Branch
drafts show the marker immediately and clear it after Revert/Discard.

## Windows CI and pending independent gate

- Added dedicated `.github/workflows/v2-m67-checkpoint.yml` Windows
  Python **3.11 and 3.12** synthetic GUI/export integration jobs,
  with M6.5 persistence, M6.6 Word geometry and M6 multilingual ZIP
  regression steps.
- Wired the same suite into the existing full V2 Windows
  `v2-inline.yml` matrix with a test-only path trigger.
- **Local focused test status:** 2 Checkpoint C end-to-end Qt tests pass
  on the Linux offscreen developer checkout. Full suite and hosted CI
  are separately checked at the final PR code head.
- **Milestone is NOT ACCEPTED until** final code, exact SHA, all
  applicable hosted Windows CI and independent architecture/security/
  export/data-integrity review have passed. Only then seek explicit
  user authorization to merge. User authorized *starting* M6.7.
- **M7 remains separate:** native installed Windows DPI/keyboard/
  clipboard/drag-drop, user-operated browser sign-in/fallback,
  complex-template/native Word matrix, all 33 RM-BE acceptance cases,
  V1 installer continuity and V2-default release certification.
  The M6.6 Word 16.0 synthetic acceptance is recorded in
  `M6_6_WORD_ACCEPTANCE.md`, not elevated to general M7 acceptance.
