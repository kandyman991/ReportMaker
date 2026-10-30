# V2 theme tokens and workspace rail

Implements the first, low-risk slice of the "Workshop" UI proposal (design canvas, direction A). It changes **chrome only**: no report data, command, project-format, exporter or web-capability behavior.

## What changed
* `v2/theme.py` — design tokens (`LIGHT`, `DARK`), a contrast helper and `stylesheet()` for the window chrome (menus, toolbars, rail, status bar, buttons, inputs, scrollbars). Applied to the V2 window only, so dialogs parented to it inherit it and nothing else in the process is restyled.
* `v2/icons.py` — a tiny stroke-icon set drawn from SVG path data with QtSvg into DPI-aware pixmaps (normal / checked / disabled). No image files are added.
* `V2MainWindow` — the tab bar is hidden and a left **workspace rail** (Modules, Editor, Photos, Assistant, Preview) drives the same `QTabWidget`. The tabs stay the single source of truth: `centralWidget()` is still the tab widget, tab texts are unchanged, and the rail highlight follows any programmatic tab change.

## Contrast is a tested contract
`tests/test_v2_theme.py` fails if any text token pair drops below WCAG 4.5:1 or any border/focus pair below 3:1, in **both** schemes. This is the regression guard for the unreadable-on-dark problems in issues #99, #101 and #103.

## Not done yet (deliberately)
* **Dark theme is defined but not applied.** `branch/canvas.py`, `branch/photo_tools.py`, `editor_tab.py`, `gallery_tab.py` and `preview_tab.py` still hard-code light colors in 27 `setStyleSheet` calls; applying dark chrome over them would be worse than today. `APPLIED_SCHEMES` documents this and is asserted in the tests.
* The command palette (Ctrl+K), floating selection toolbar, inspector panel and the Assistant drawer from the proposal are separate changes.
* Rail labels are "Photos" and "Assistant"; the underlying tab texts ("Photo Gallery", "ChatGPT") are unchanged for existing callers.

## Verification limits
Offscreen Qt on Linux only. Not checked: real Windows rendering and DPI scaling, Windows 11 native style interaction with the style sheet, or the **frozen** app — the packaging gate should confirm that `PySide6.QtSvg` is collected by PyInstaller after this change. Physical installed-Windows acceptance (the 33 RM-BE cases) is unaffected and still pending.
