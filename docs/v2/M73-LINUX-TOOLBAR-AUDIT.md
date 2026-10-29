# M7.3 Linux native toolbar audit (non-release evidence)

Environment: Lenovo Legion `mircea-gitmachine`, Ubuntu 26.04.1 LTS, GNOME/Wayland,
PySide6 6.12.0. This audit uses only synthetic report and image data. The original
source snapshot was `805b482b65efa0f17d4d306a374a734e84357966`.

## Finding and remedy

The original `v2BranchActions` toolbar contained 27 commands. The native audit
found 19 inaccessible inline buttons at 800 px, 13 at 1280 px, and 11 at
1600 px: insert photos, arrange, delete, contents, and Undo/Redo could fall
into Qt's overflow extension. This is a discoverability and accessibility
regression, irrespective of whether QAction shortcuts still work.

The project, editing, and navigation command groups now occupy three fixed
toolbar rows, with explicit Project, Languages, Insert, Arrange, Navigate,
and View menus. Existing QAction object names, shortcuts, callbacks and
draft-safety behavior remain intact; the UI makes no new persistent state.
The three priority insert buttons remain directly visible.

## Verification

- Native Wayland GUI screenshots captured at 660, 800, 1024, 1280,
  and 1600 px; none of the 41 registered V2 commands are lost and no
  direct command or menu button is clipped.
- Offscreen Qt tests verify all QAction references are reachable via a
  visible toolbar control or a labeled menu, actual mouse-event selection
  of an Insert menu command changes the canonical report, Undo restores the
  report, and `Ctrl+Shift+I` still dispatches with its menu closed.
- Linux native controls support Add module/submodule/paragraph, staging and
  applying drafts, synthetic file drop through Qt MIME, gallery placement,
  project save/reopen, and DOCX/PDF export.
- The full unit-test suite passes; see CI for authoritative result on
  the final commit.

Evidence is stored locally on the Legion under
`/home/mircea/ReportMaker-linux-audit-evidence/` and not committed
(synthetic screenshots, local temporary project, logs).

## Explicit limits

- The Wayland compositor refuses the synthetic test harness's popup-input
  grab without hardware input. Menu action dispatch is checked on native
  Wayland and actual popup mouse selection is checked in offscreen Qt; **an
  external physical mouse interaction through the native Wayland menu has
  not been independently certified**.
- A Qt MIME event exercising gallery file-drop handling is **not** equivalent
  to dragging a file from a separate OS application.
- This Linux check does not satisfy the 33 physical installed-Windows
  `RM-BE` M7.3 acceptance cases. V1 and the Windows release gate are unchanged.
