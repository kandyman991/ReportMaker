# M3.1 — Inline Heading Editing and Mixed-Order Heading Insertion

**Date:** 2026-10-28. **Baseline:** merged M2.4 on live main at 9dbd22b0896f644cd1e2991536c3ba4d13e1a820. **Working branch:** feature/v2-m3-1-heading-editing. **Requirements:** BE-E01, BE-E06, architecture one-canonical-report contract.

## Scope

- Headings (levels 1–6) are native blocks in the same canonical ordered module blocks collection; no V2-specific parallel text/table model.
- The command gateway accepts add_heading with an explicit validated heading level and optional mixed sibling index, plus set_heading_rich. Validation rejects wrong block types, invalid level/index, foreign IDs, stale revisions/generations and pending drafts. A successful edit is one undoable transaction.
- Direct inline heading editor uses the existing natural-height, scrollbar-free InlineParagraph and Apply/Revert draft coordinator. Safe text/rich remapping preserves unchanged styled code points; original language, translations, stale-language provenance and heading level persist in canonical project data.
- Toolbar **+ Heading** appends to the active module. Each existing content-block context menu offers **Insert heading after**, using that block's validated mixed index. Module context menu supports **Insert heading inside**. Insertion into a collapsed module reveals the new heading, and local collapse persistence is updated without changing report document data.
- Reuses existing PDF/DOCX/export model unchanged; no new schema, V1 UI import, browser/ChatGPT automation, media, installer or release change.

## Tests and safeguards

- tests/test_v2_heading.py (8 cases after review): pure commands, level/type/index rejection, exact mixed insertion, Undo/Redo/no-op behavior, multi-language provenance, Unicode style rebase and draft conflict; Qt inline editing, collapsed insertion, natural height/hidden internal scrollbars, save/reopen, and UTF-16 caret/selection restoration after Apply.
- .github/workflows/v2-inline.yml gates the new tests on Windows Python 3.11 and 3.12 and reruns M1.3, natural-height and M1.2 compatibility. Exact final-branch-head hosted results must be checked before review/merge.
- Local offscreen Linux checks ran 111 test_v2_*.py tests with PySide6, including new M3.1 tests. Qt/offscreen does **not** replace installed Windows acceptance at 100%, 125%, 150% DPI, keyboard/screen-reader tests or long nested reports.

## M3 remains incomplete

M3.2 must add a genuine contextual **rich-text** toolbar with visible selection formatting, proper focus/Unicode handling, and formatting persistence/Undo across paragraphs and headings. M3.3 must add guarded inline table cells and row/column operations. M3.4 must provide remaining typed block insertion and full positional UI, clarify width/height persistence, and coordinate cross-tab drafts when the separate Editor tab is integrated. Full Checkpoint B remains pending these gates, native Windows acceptance and independent review. Do not merge/release without explicit authorization.

## Independent review correction (PR #77)

- Fixed a redundant session-notification redraw that replaced freshly restored inline editors after commit; retained synchronous toolbar/UI updates and deferred native drag protection.
- Fixed QTextCursor restoration clamping by counting UTF-16 code units for astral Unicode rather than Python code points.
- Added an offscreen Qt regression covering emoji caret and selection after Apply. Corrective source/test commit: `95c445d8617dcc1fbef694977ebe6bc9b47ac744`.
- Independent Linux/offscreen Python 3.14 environment: **112** `test_v2_*.py` regressions passed; `compileall` and `git diff --check` passed. Hosted Windows 3.11/3.12 exact-final-head workflow checks and installed-Windows visual/DPI/accessibility acceptance remain separate.
