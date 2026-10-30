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

## The same tool in both panes
Every tab holds **its own copy** of a tool, so Modules (or Editor, Preview, Photos,
Assistant) can be open in the left and the right pane at once. Picking a tool for a tab
never takes it from another tab. The window's first copy of each tool is the attribute
(`branch`, `editor_tab`, ...) that existing code uses; extra copies come from factories.

What keeps copies from interfering:
* **One session, one draft coordinator.** Every copy shows the same report and shares the
  one `DraftCoordinator` (so there is still a single draft guard on the session).
* **A draft owner id per copy.** Modules copies stage as `branch`, `branch-2`, ...; Editor
  copies as `page-editor`, `page-editor-2`, .... A field being edited in one copy turns
  read-only, with that draft's text, in every other copy (Modules or Editor) and unlocks
  when the draft is applied or reverted. Typing into a locked field changes nothing.
* **Assistant copies share one browser profile** (`SharedBrowserProfile`), so there is one
  login and no clash between two profiles using the same storage path.
* **A new copy starts with the current page style** (template/footer) of the first one.
* **Closing a tab** parks the first copy (state kept) and deletes an extra copy, **unless the
  extra copy still holds unapplied edits**: then it is kept hidden so those edits are not
  orphaned; opening Modules in an empty tab brings it back, and Save's Apply/Discard/Cancel
  prompt covers every copy.
* **Limits.** At most 4 copies of a tool and 8 tabs per pane (each Assistant copy is a web
  view). Hitting the limit leaves the tab as it was and says so in the status bar.

## Toolbars act only on the visible Modules
The *Module editing* and *Branch navigation* toolbars (and Contents) are Modules commands.
They act on `V2MainWindow.modules_target()`:
* the Modules copy in the **active pane**, or if that pane shows another tool, the Modules
  copy in the **other visible pane**;
* never a copy that is hidden behind another tab or parked;
* if no Modules is visible, the commands, their drop-down buttons and their shortcuts are
  **disabled** (tooltip: "needs a visible Modules tab"), and the callbacks refuse if reached
  some other way. The Photos tool inserts only into a visible Modules for the same reason.

New / Open / Save / Save As / Report info / Customers / Languages / Layout template are
project commands and stay enabled whatever tool is showing. Undo and Redo are Modules
commands today (they are disabled while only the Editor is visible).

## Code
* `v2/workspace.py` is arrangement only: `Workspace` (two `WorkspacePane`
  `QTabWidget`s in a `QSplitter` named `v2WorkspaceSplitter`), `ToolPicker`, the
  tool list, copy management and the saved state. It knows nothing about reports or drafts.
* `V2MainWindow.tabs` is now the `Workspace`. The old `QTabWidget` calls
  (`setCurrentWidget`, `currentWidget`, `widget`, `count`, `tabText`, ...) still work,
  addressing tools (and the exact copy for `setCurrentWidget`/`currentWidget`) rather than tab positions, so existing code and tests are unchanged.
* The window refreshes **every visible copy** (not only the current tab) after a
  session change or when drafts appear/clear: Preview beside Modules follows an
  applied edit without switching tabs. The Assistant only loads its website when it
  becomes visible.
* The window's minimum width is 960 px with the split on (two usable panes) and
  660 px otherwise.
* In a narrow single-pane window (up to 720 px), the left rail switches from
  text-under-icons to compact icons. Action tooltips and accessible names remain
  available; labels return automatically when the window grows. This preserves
  the 20-level/660px canvas-fit regression without reducing the 6 px minimum
  connector step. Hosted Windows freezing explicitly collects QtSvg and checks
  the workspace, theme, icons, and all retained shared engines.

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
separate copies, kept drafts after a move, Preview following edits, activation only
when visible, and the Editor page width. Three tests that put Modules and Editor side by
side, two Modules or two Editors locking each other, and the toolbar scoping are covered too.

## Not done / limits
* Offscreen Qt on Linux only. Not checked: native Windows rendering and DPI, the
  frozen app, real window sizes below 960 px with the split on.
* At 160 % zoom in a half-width pane on a 960-1100 px window, a card can be wider than the
  pane by a few to ~100 px (the canvas has no horizontal scrollbar; use the Pan commands, zoom
  out, or turn the split off). Checked across the five stress scenarios x 960/1100/1366/1920 px x
  55/100/160 % zoom with Modules beside the Editor, and with two Modules side by side: no overlap or clipping anywhere, and overflow in
  4 of those 60 combinations, all at 160 %.
* Tabs cannot be dragged between panes (use *Move to the other pane*). Dragging a module
  from one Modules copy onto another is refused (each copy only accepts its own drags).
* The view state remembered per project (selection, scroll, collapsed modules) comes from the
  first Modules copy.
* Editor has no toolbar commands yet (Undo/Redo and Find act on Modules only).
