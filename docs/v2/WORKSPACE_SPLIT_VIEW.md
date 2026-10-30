# Two-pane workspace and per-tab tool picker

Builds on `UI_THEME_AND_RAIL.md`. It changes how the existing tools are arranged
on screen; no report data, command, project-format, exporter or web-capability
behaviour changes.

## What the user gets
* **Split view.** The workspace can be divided into a left and a right pane
  (rail button *Split* at the bottom, or **Ctrl+\\**). Each pane has its own tabs.
* **Pick the tool for every tab.** The small **▾** on each tab lists the tools
  (Modules, Editor, Photos, Assistant, Preview) and switches that tab in place.
  **+** opens an empty tab that shows one tile per tool. Right-click a tab for the
  same menu, plus *Move to the other pane* and *Close tab*.
* **The rail** opens a tool: if it is already in a tab that tab is selected,
  otherwise it opens in a new tab of the active pane (or fills an empty tab).
* **Remembered layout.** Split on/off, which tool is in which tab, and the pane
  sizes are saved per user (Qt settings), never in a report project. First run is
  Modules on the left, Preview on the right.

## The rule that keeps it safe
Each tool is **one widget owned by the window**, and it is open in **at most one
tab**. Choosing a tool that is open elsewhere *moves* it (the tab it left becomes
an empty tab, or disappears if its pane has other tabs). So there is still exactly
one report session, one set of drafts and one browser view, and moving a tool never
loses an unapplied edit. Two copies of Modules would need two draft owners per
field, which is the interference this work removes.

## Code
* `v2/workspace.py` is arrangement only: `Workspace` (two `WorkspacePane`
  `QTabWidget`s in a `QSplitter` named `v2WorkspaceSplitter`), `ToolPicker`, the
  tool list and the saved state. It knows nothing about reports or drafts.
* `V2MainWindow.tabs` is now the `Workspace`. The old `QTabWidget` calls
  (`setCurrentWidget`, `currentWidget`, `widget`, `count`, `tabText`, ...) still work,
  addressing tools rather than tab positions, so existing code and tests are unchanged.
* The window refreshes **every visible tool** (not only the current tab) after a
  session change or when drafts appear/clear: Preview beside Modules follows an
  applied edit without switching tabs. The Assistant only loads its website when it
  becomes visible.
* The window's minimum width is 960 px with the split on (two usable panes) and
  660 px otherwise.

## Fixed on the way: Editor page width
The Editor's paper was centred in a scroll area, which gives a centred widget at most
its size hint, so the page shrank to about 320 px instead of the printable width and
its text boxes wrapped early and were clipped. The paper's hint is now the printable
page width. This was visible in single-pane mode too and mattered more in a half-width pane.

## Changed invariant
The "no legacy three-panel UI" smoke checks used to require *no* `QSplitter` in the V2
window. They now allow only the workspace's own `v2WorkspaceSplitter`; any other splitter
still fails them (`__main__.py`, `test_v2_shell.py`, `test_v2_lifecycle.py`).

## Tests
`tests/test_v2_workspace.py`: default arrangements, picking tools per tab (menu, picker,
rail), moving/closing/un-splitting, saved-state round trip and damaged-state fallback,
single widgets and kept drafts after a move, Preview following edits, activation only
when visible, and the Editor page width. Three tests that put Modules and Editor side by
side run once PR #114 (draft sync between them) is in the tree and are skipped before that.

## Not done / limits
* Offscreen Qt on Linux only. Not checked: native Windows rendering and DPI, the
  frozen app, real window sizes below 960 px with the split on.
* At 160 % zoom in a half-width pane on a 960-1100 px window, a card can be wider than the
  pane by a few to ~100 px (the canvas has no horizontal scrollbar; use the Pan commands, zoom
  out, or turn the split off). Checked across the five stress scenarios x 960/1100/1366/1920 px x
  55/100/160 % zoom with Modules beside the Editor: no overlap or clipping anywhere, and overflow in
  4 of those 60 combinations, all at 160 %.
* Tabs cannot be dragged between panes (use *Move to the other pane*); a tool cannot be
  shown twice at once (by design, see above).
* The top toolbars still act on Modules even when Modules is not the visible tool;
  scoping them per tool is separate work.
