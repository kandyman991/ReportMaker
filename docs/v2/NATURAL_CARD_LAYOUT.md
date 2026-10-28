# V2 Natural-Height Cards — Qt Layout Contract

**Decision:** User-confirmed 2026-10-28. **Framework:** retain PySide6 / Qt Widgets; this is *not* a move to Jetpack Compose or Tauri.

## Required behavior

1. All expanded branch cards derive their height from **complete content**: no arbitrary maximum content height, no internal text/photo/table viewport scrolling, no truncated text.
2. The branch is one continuous document-like vertical hierarchy. **No visible scrollbars** in the Branch Editor, including the workspace; the sole outer scroll offset remains available for wheel, touchpad, keyboard and focus/caret reveal.
3. Changing window width reflows text and updates every affected card's natural size. Growing and shrinking cards must not overlap adjacent cards or detach connectors.
4. Parent Qt layouts own card geometry; QPainter draws connectors only. Do not substitute absolute X/Y positioning to satisfy resize cases.
5. Inline drafts, canonical report content, rich-text formatting, selection, Undo/Redo and project persistence are independent of card sizing. Zoom and future photo/table widgets must honor the same intrinsic-height rule.
6. Normal branch editing must be responsive for many nodes; full widget-tree rebuild remains an independent performance optimization task (targeted updates/virtualization), not a reason to impose a fixed card height.
7. Nested modules must not silently clip content at deep levels; adaptive indentation and wide-content cases need subsequent regression coverage before M2 UI acceptance.

## Current implementation

- `BranchCanvas` is a `QScrollArea` with a `QVBoxLayout`; scrollbars are hidden but its vertical scroll offset remains functional. `QLayout.SetMinAndMaxSize` allows dynamic child sizes to change the scrollable document height.
- `InlineParagraph` is a `QPlainTextEdit` with fixed **vertical size policy**, *not fixed pixel height*: its `sizeHint` computes the pixel height of all wrapped text blocks from Qt's live document layout. This handles CJK/emoji font fallback heights that are not represented by the plain document line-count. No minimum 74px or maximum 230px restriction remains; one-line content shrinks.
- Both internal editor scrollbar policies are AlwaysOff. Wheel events over an editor go to the single outer scroll viewport, and focused caret movement reveals the caret through the outer scroll offset.
- Photo/table blocks are not yet rich V2 content widgets; they remain textual stand-ins. Their future visual renderers must satisfy this contract before release. Images should scale to available card width while preserving aspect ratio; tables should grow by rows and wrap cell content instead of adding internal scrollbars.
- Module headings currently use single-line `QLineEdit`, so exceptionally long titles can horizontally pan internally; a wrap-capable title editor must be reviewed and tested to satisfy the full all-content-visible contract. This PR specifically implements intrinsic multiline paragraph sizing and removes visible Branch Editor scrollbars.

## Automated acceptance and remaining gates

`tests/test_v2_natural_cards.py` covers natural height above the old 230px cap; long CJK/emoji text and full final character visibility; no internal scrollbar scroll range; reflow on narrower/wider windows; shrink after content deletion; adjacent-row non-overlap; visible-scrollbar prohibition; wheel navigation when hovering inside text; keyboard caret reveal; and canonical commit/Undo/Redo.

Linux Qt offscreen tests are **not** installed Windows acceptance. Verify on actual Windows at 100/125/150% display scale, on very narrow windows, with thousands of blocks, long/wrapped titles, tables/media, deep nested modules, touchpads and assistive technology. External ChatGPT browser scrolling is not governed by this Branch Editor-only rule.
