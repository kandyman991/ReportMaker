# Windows v0.5.0 RC1 — installed UI acceptance findings

Date: 2026-10-27. Status: **RC1 NOT ACCEPTED / stable promotion BLOCKED**.
User tested the actual published RC1 installer, pinned application source
`1e092c175857bfd5969202201b2595604bb27b2f`.

## RC1-F01 — invisible report preview (blocking)
The actual Windows screenshot shows editable modules, the content selector and the
ChatGPT manual browser operational. The document preview instead renders dark
body text over a dark surface, causing substantial loss of readability.
Cause confirmed in code: `_render_preview()` hardcodes dark HTML text color
`#252525`, while `QTextBrowser` inherits the dark Qt theme background.
Targeted isolated fix: [PR #22](https://github.com/kandyman991/ReportMaker/pull/22),
with a theme-independent white document canvas, larger preview split and
A-/A+ view zoom. Regression: Windows Qt offscreen viewport pixel should be
light and zoom widgets present. An updated Windows installer and installed-PC
retake are required: hosted CI is insufficient.

## RC1-F02 — edit report fonts/styles/size (blocking)
The installed editor exposes plain-text entry but no font formatting controls.
User requires font family, font size in points, bold/italic and other styling,
alignment and typographic sizing. Formatting must remain editable after saving,
survive Undo/Redo and portable .rmproj migration, and match the editable Word
runs and print PDF. See [issue #23](https://github.com/kandyman991/ReportMaker/issues/23).
Do not mistake preview zoom for a saved font size.

## RC1-F03 — DOCX page layout/letterhead import (blocking)
User attached a real-world corporate DOCX letterhead privately to this ChatGPT
conversation as a **reference only**, not an upload to the public repository.
Its structural characteristics were inspected locally:
- Portrait A4 document, 21.0 x 29.7 cm.
- Margins: top 2.5 cm; bottom 2.0 cm; left/right 2.0 cm.
- Header/footer offset each about 1.25 cm.
- Header includes an embedded brand logo.
- Multi-line contact footer includes formatted text, alignments/tab stops
  and embedded pictograms. Body contains essentially no report content.
- The template also contains style definitions; some footer labels are
  Calibri 8pt while the Normal style is Times New Roman 10pt.

ReportMaker must safely import original DOCX/DOTX page dimensions, styles,
header/footer, logos and decorations into reusable portable template data,
without modifying the external original document, exposing private content in
GitHub, or silently dropping complex Word elements in PDF output.
See [issue #24](https://github.com/kandyman991/ReportMaker/issues/24).
A template import that copies only paper size and logo is **not** considered
sufficient for acceptance.

## Release decision
No stable production release, PR merge, Windows installer overwrite, or
successful installed-Windows acceptance should be claimed based on RC1.
Existing immutable [RC1 prerelease](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-v0.5.0-rc.1)
remains an audit reference. Historical M0 remains available as fallback.
After fixes and regression review, build **RC2** from the corrected exact
commit, independently verify installer hash and rerun actual native
Windows/Word/PDF acceptance using synthetic project samples. Never upload
the user screenshot or corporate document to the public repository.
