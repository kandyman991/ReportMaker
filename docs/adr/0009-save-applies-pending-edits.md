# ADR-0009 — Explicit resolution of unapplied edits at Save and project transitions

Date: 2026-10-30
Status: **Accepted — option B (explicit confirmation)**, replacing the original proposed automatic-apply behavior in PR #111
Owners: ReportMaker project
Scope: V2 Save, Save As, New, Open and Close; issue #98 / draft PR #97

## Problem and constraint

Typing in Modules or the page Editor creates a staged draft outside the canonical report, with a specific editor owner and original source baseline. Structural commands, Undo/Redo, export and unrelated operations remain blocked while drafts are pending.

Native Windows testing of issue #98 found that users could type into an editor, then be blocked on Save while Apply/Revert controls were easy to miss. Making Save automatically commit every pending draft would remove that particular obstacle but violate issue #98's **no silent auto-commit** requirement, especially for New, Open and Close.

## Decision

1. **No implicit draft changes.** Save and Save As with pending drafts present an explicit modal with three visible buttons: **Apply and save**, **Discard edits**, **Cancel**. Cancel is the default and escape action. Discard edits saves only previously applied content and intentionally loses staged drafts; the dialog describes that consequence.
2. **Project transitions.** New, Open and window Close with pending drafts show **Apply edits**, **Discard edits**, **Cancel**, with Cancel the default. After an explicit Apply/Discard, the existing **Save / Discard / Cancel** question for committed but unsaved report changes still runs. The second Cancel keeps the current project and any already explicitly applied edits. The draft-confirmation prompt never appears if no drafts are pending.
3. **Atomic apply.** Approved Apply collects drafts from both Modules and Editor and checks generation, source baseline and validation before one gateway transaction and one Undo entry. A failed apply does not save, switch, close or clear any draft and explains how to recover via the yellow panel or Editor tab.
4. **Explicit discard.** Confirmed Discard clears pending fields from both editors, leaving the canonical report, its revision and current saved file unmodified until the normal Save/transition succeeds. This deliberately discards staged content **only** because the user chose Discard.
5. **Picker cancellation.** Save/Save As requires a chosen destination and any required overwrite consent **before** changing pending drafts. Open obtains a file path before prompting; closing any picker without selecting a file leaves all pending edits and the canonical report untouched.
6. **Unchanged guards.** Insert, move, drag/drop, photo import, exports, unrelated dialogs and Undo/Redo continue to reject unresolved drafts. The yellow per-card recovery panel and its confirmation remain. No timer-, focus-out- or background-based autosave, and no V1/report/archive/schema changes.

## Rationale and alternatives

Option **B** is accepted because it keeps Save usable while obtaining the explicit user approval required by issue #98. Option **A** (reject Save and point to the yellow panel) is safe but leaves the observed usability blocker. Option **C** (setting) introduces unnecessary variability; option **D** (silent autosave on focus/timer) is rejected. The original proposed automatic apply is **not accepted**.

## Verification and release gates

- tests/test_v2_save_applies_drafts.py: explicit dialog labels/default Cancel, two-editor atomic apply and Undo, two-editor discard, validation rollback and ownership isolation.
- tests/test_v2_lifecycle.py: Save/Save As Apply/Discard/Cancel; New/Open/Close canceled transitions; Save/Open picker cancellation, stale drafts, legacy Save As and project identity.
- tests/test_v2_m73_native_draft_recovery.py: blocked structural actions, explicit Save and failed apply with visible recovery.
- Full Legion tests and exact corrected-head Windows CI required before integrating PR #111 into the M7.3 branch.
- Physical installed-Windows 33-case M7.3 acceptance, including #98, remains pending. Neither GitHub CI nor this ADR authorizes production release, installer publication or a merge of PR #97 to main.
