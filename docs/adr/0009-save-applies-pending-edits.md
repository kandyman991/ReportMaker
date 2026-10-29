# ADR-0009 — Save, Save As, New, Open and Close apply pending inline edits

Date: 2026-10-29
Status: Proposed — needs an explicit owner decision because it departs from the expected behavior written in issue #98
Owners: ReportMaker project
Supersedes: None. Refines the pending-draft guard from M1.3 and the M7.3 visible-recovery work (issue #98, PR #97).

## Context

Typing in the Branch Editor or the page Editor creates a **draft** that is not part of the canonical report until it is applied. Until now an unresolved draft blocked ordinary commands, Undo/Redo, **Save** and project switches.

On physical Windows (issue #98) users typed text, pressed Save and got a modal refusal, while insert and drag also appeared inert. PR #97 added a visible yellow recovery panel ("Apply all edits" / "Discard edits…") and clearer blocked-command messages. Issue #98's expected behavior states *no silent auto-commit*.

The owner has since asked that **Save apply pending edits automatically**. This ADR proposes that as a narrow, explicit, undoable exception, and records the alternatives so it can be accepted, changed or rejected on review.

## Decision

1. **Explicit actions only.** Save, Save As, New, Open and closing the window — each a deliberate user action — first apply **all** pending drafts (Modules and Editor together) as **one undoable change** through `DraftCoordinator.apply_all()`, then continue. The status bar says: "Pending edits applied as one change — Undo available".
2. **Atomic and fail-closed.** Every draft baseline and owner is inspected before anything executes. If any draft cannot be applied (for example its source changed, or validation fails), **nothing** is applied, saved, switched or closed, every draft stays exactly as typed, and a modal names the reason and points to the yellow panel (Modules) or the Editor tab.
3. **Everything else stays as in PR #97.** Insert, move, drag, photo import, Undo/Redo, exports, Report info, translations and template import remain blocked while drafts are pending, with the recovery panel. Discard still needs confirmation. There is **no timer, focus-out or background autosave**: nothing is applied unless the user chose one of the actions in (1).
4. **Switching projects.** After the drafts are applied the usual Save / Discard / Cancel question for unsaved changes runs. Discard drops the applied edits as well; Cancel keeps them applied (still undoable).
5. **Cross-editor drafts.** Drafts from different editors are applied in one batch with the existing stale-source check; no editor can overwrite canonical content it did not start from.

## Why this departs from issue #98

"No silent auto-commit" protects against edits being committed or discarded without the user knowing. This change is not silent — it runs only when the user presses Save (or switches/closes), is announced, and is one Undo away — but it **is** a commit the user did not confirm separately. If the owner reads #98 strictly, choose alternative B.

## Alternatives considered

* **A. Status quo (PR #97):** Save refuses and points to the panel. Strictest, but Save is the one command people expect to simply keep their text; this is what blocked the Windows acceptance run.
* **B. Prompt on Save:** "Apply and save / Discard / Cancel" when drafts are pending. Satisfies "deliberate" literally at the cost of one more click each time. The recommended fallback if this ADR is not accepted as written.
* **C. A setting, default off.** Adds a preference surface for one behavior.
* **D. Autosave on focus-out or timer.** Rejected: silent, and it would apply half-typed text.

## Consequences

* Removes the most common Save blocker and the risk of losing typed text on close.
* One more code path commits drafts; exports and several dialogs still require edits to be applied first and could follow the same pattern later.
* If accepted, update: the `drafts.py` module docstring, `docs/v2/M1_3_INLINE_BRANCH.md`, and the expected-behavior text of issue #98.
* Does **not** validate or replace the physical installed-Windows retest of #98 / BE-L01.

## Verification

`tests/test_v2_save_applies_drafts.py` (coordinator `apply_all`: no-op, cross-editor single undo step, failure keeps every draft, named batches still reject other editors' fields; Save from Modules + page Editor drafts is one undo step and round-trips), `tests/test_v2_lifecycle.py` (Save, Save As, New, Open and Close apply then prompt; an unappliable draft refuses and is kept) and `tests/test_v2_m73_native_draft_recovery.py` (the recovery panel and blocked commands are unchanged). Offscreen Qt only; synthetic data.
