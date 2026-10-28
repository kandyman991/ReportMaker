# M2.3 — Indent / Outdent, Duplicate and Delete

**Status:** Isolated implementation pending PR review, hosted Windows checks and installed-PC acceptance.
**Base:** live `main` 8229321276a7207c5faa455942b38d3a23404b8 (post-M2.2 PR #72).
**Branch:** `feature/v2-m2-3-structural-actions`.
**Requirements:** BE-S05, BE-U04; M2 structural editing exit criteria.

## Interaction contract

- The Branch Editor toolbar exposes Indent, Outdent, Duplicate, and Delete for the selected intervention module, with enabled state derived from canonical model projections. Shortcuts: Alt+Shift+Right, Alt+Shift+Left, Alt+Shift+D, Ctrl+Shift+Delete. Ordinary Backspace/Delete remains available within inline text fields.
- Every movable row (modules and mixed typed leaves) has a ⋯ menu plus right-click on the card background. The row menu provides duplicate/delete for text, heading, photo, table and page break placements; module menus also provide indent/outdent.
- Indent is permitted only if the **immediately preceding mixed sibling** is a module. It moves the selected module INSIDE that sibling, at the end of its children. If a paragraph/photo/table appears immediately before the selection, Indent is disabled: no silent jump across content.
- Outdent moves a nested module **one level outward and immediately after its former parent** in canonical order. Neither operation changes a moved module ID, its descendants, translations, or associated media. Nested-to-nested moves preserve the wrapper ID; nested-to-root necessarily removes the wrapper.
- Duplicate inserts a copy immediately after the selected object. Every duplicated module, nested wrapper and descendant block gets a new persistent ID. Duplicated leaf blocks get a new block ID and retain rich formatting, translations, photo placement geometry, captions and the same existing logical asset reference. No additional image bytes or second gallery are created.
- Delete asks for explicit confirmation (default No), removes the selected module/subtree or leaf report placement, and supports one-step Undo/Redo. Original external files and immutable project-owned image bytes are not edited. Removing the last *placement* of a project asset affects subsequent archive reachability, not the source file.
- Root and mandatory final Conclusions cannot be duplicated or deleted. Conclusion content blocks remain individually editable/removable. The planner rejects invalid owners, stale report generation/revision, pending drafts, malformed addresses, and out-of-range requests *without history mutation*. A modal confirmation captures the original generation/revision, preventing a queued project switch or intervening edit from deleting a different node.
- Both indentation controls use M2.1's existing `plan_drop` and `move_node`; duplicate/delete use the existing pure transactional `ProjectEditor`. The Branch Editor never persists or owns an independent tree.

## Automated verification

- `tests/test_v2_actions.py`: synthetic deep duplicates with fresh IDs; source translations/media/placement retention and Save/Open; mixed typed leaf clones; undo/redo of subtree deletion and promotion; wrapper preservation; strict indent positioning, invalid and stale intents, draft guards; Qt toolbar/menu and confirmation, including a session switch during a modal confirmation.
- `.github/workflows/v2-structure.yml`: hosted Windows, Python 3.11 + 3.12, with the new suite and existing M2.1/M2.2 and M1.2–M1.4 checks. Exact final PR head must pass before merge.
- Existing v4 project format and export derivation remain unchanged; V1 UI, browser-only ChatGPT integration, installer and main release are untouched.

## Manual installed-Windows acceptance (not yet done)

1. Select a top-level module and use toolbar and Alt+Shift+Right/Left to indent/outdent; verify visual connectors, focus, Undo/Redo and order after Save/Open.
2. Try Indent with an intervening paragraph/photo/table, and with the first sibling: actions should be disabled with no unexpected nesting.
3. Nest several levels and outdent once; verify the selected module emerges directly after its former parent, not at the end of another branch.
4. Use ⋯ or right-click on a module, heading, paragraph, table, photo and page break; duplicate, delete (No/Yes), Undo/Redo, and verify all child content, translations and photo placements remain correct.
5. With unapplied drafts, verify destructive actions and moves are blocked without losing draft text. Try text selection, Backspace/Delete, and all shortcuts in focused inline fields.
6. Test on an installed Windows x64 system at 100%, 125% and 150% display scaling; check keyboard focus, screen reader names, modal dialogs and long-branch scrolling.

## Deferred

M2.4 expand/collapse presentation persistence, descendant counts, derived numbering and visible TOC. No physical installed-Windows validation or installer/release authorized. Independent PR review and explicit merge approval are required.

## PR #74 integration review — 2026-10-28

- After PR #75 merged, integrated the newer `main` (`00bfb0169241af03a90bf68deba81e5fe475f7d0`) without reverting its intrinsic-height Qt paragraph editor, hidden workspace/editor scrollbar policies, wrapping and caret/wheel navigation.
- Resolved the overlapping `canvas.py` imports by retaining both M2.3 `QMenu`/`QMessageBox` and PR #75 layout classes (`QLayout`/`QSizePolicy`).
- Added a combined Qt regression in `test_v2_actions.py`: commit a long multilingual paragraph, duplicate it, verify both expanded cards and hidden scrollbars, check adjacent row geometry, delete with confirmation, and Undo to restore.
- Local Linux/offscreen full synthetic suites pass; exact merged-head hosted Windows workflows must pass before merge. Physical installed-Windows DPI/assistive-technology acceptance remains open.
