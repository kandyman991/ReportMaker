# M3.2 — Contextual Rich-Text Formatting Ribbon

**Started:** 2026-10-28. **Baseline:** live main after merged PR #77, a5537872eaeb6bbe403034250ffa02d2c7222914. **Branch:** feature/v2-m3-2-contextual-rich-ribbon. **Contracts:** BE-E01, BE-E07, BE-L04, BE-I01, BE-I03.

## Delivered scope

- The compact formatting ribbon appears only for the focused inline paragraph/heading. Inactive cards have no formatting bar; a ribbon is instantiated only on the first focus of a particular editor. The native title editor remains separate from the rich-text toolbar.
- Accessible icon-like controls with visible checked states: **Bold, Italic, Underline, Strikethrough, A−/A+ (font sizing), left/center/right/justified alignment, bullet/decimal lists**. Standard Ctrl+B/I/U shortcuts reuse the same staging path. Character commands require an explicit nonempty selection; paragraph commands accept a caret or selection.
- Toolbar controls have Qt NoFocus, preserving text selection and caret. All Qt UTF-16 selection offsets are converted to the canonical model's Unicode code-point offsets, without allowing half of a surrogate pair. A font size change or alignment may expand the widget's natural height; no inner/workspace scrollbars are introduced.
- Pure, validated run/paragraph transformations preserve all unmodified typography properties and coalesce adjacent equal runs. Paragraph styling excludes the next paragraph if a selection ends at its first character; contiguous decimal-list paragraphs share one native Qt list so numbering does not restart at 1.
- Formatting-only drafts, combined text-and-formatting drafts, Apply/Revert, stale source rejection, revision guard, Save/Undo barriers and formatting rebase after typing use the **existing canonical CommandGateway**. Every successful Apply is one Undo/Redo transaction. Source wording and translations remain distinct; format-only edits do **not** mark translations stale.
- Qt QPlainTextEdit remains the natural-height in-place input. Its rich projection is a temporary UI view, **not** a saved HTML document, alternate report model, or V1 rich_editor dependency. Canonical character styles use QSyntaxHighlighter so typing, selection and native Ctrl+Z do not acquire phantom formatting-undo actions; paragraph/list geometry uses Qt block formats only when required. The existing allowlisted RichFormatting data is consumed by project saving and export without a schema change.

## Explicit boundaries

- UI changes are confined to the V2 Branch Editor and dedicated V2 formatting/preview adapters. Existing formatting attributes (including pre-existing font families/colors/highlights/baselines) are retained when other attributes change, but their editing controls are not yet exposed in this first contextual ribbon. Full typography polish, accessible palette/family pickers and nested list/indent controls need separate user acceptance.
- M3.3 inline table cell, row and column editing and M3.4 remaining block insertion/cross-tab conflict handling are not delivered. No V1 UI change, WebEngine/ChatGPT integration change, schema migration, exporter change, release, or RC PR #21 change.
- Offscreen Qt + GitHub-hosted Windows CI is not physical Windows validation. Native installed-Windows acceptance at 100/125/150% DPI, screen reader/keyboard, mouse/focus behavior and long real-world multilingual reports remain required.

## Repeatable gates

- PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p 'test_v2_*.py'
- python -m compileall -q src/reportmaker/v2 tests/test_v2_formatting.py
- git diff --check
- .github/workflows/v2-inline.yml adds test_v2_formatting.py on hosted Windows Python 3.11 and 3.12; require passing **exact final PR-head** hosted workflow results before merge.
- Regression cases cover active-only contextual controls, focus/selection preservation, Unicode offsets, staged formatting, paragraph/list semantics, keyboard shortcuts, undo/redo, translation provenance, Save/reopen and invalid/stale commands. Independent review added typing-after-formatting / native Ctrl+Z projection tests and a heading weight-inheritance check (16 formatting tests, 128 local V2 tests).

**Next action:** independent review of draft PR, run exact-head Windows hosted CI and address findings before user-authorized merge. Then proceed to M3.3.
