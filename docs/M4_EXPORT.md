# M4 — Editable DOCX and local PDF export (PR #13 merged, layout follow-up in review)

Status: M4 initial implementation PR #13 is merged to main with PR #14 corrections; optional export branding and photo-layout refinements are proposed in a separate reviewable PR. **Not installed-PC acceptance, an approved installer, or a production release.**

## Source of truth and export boundary
- \`.rmproj\` remains the only canonical editable ReportMaker project. Exports are generated projections; editing a Word document does **not** update the underlying \`.rmproj\`. The user may reopen the project and export again.
- \`prepare_export(ReportProject)\` performs read-only \`validate_report_tree\` and uses \`module_outline(report)\` for section numbers, heading positions and Summary. Contents and tree are not independently persisted.
- Original/source text is used at M4. A report's arbitrarily tagged language records and stale translations are preserved in the project, but automatic translation selection and multilingual presentation are **M5**, not silently emulated through fallback copies in M4.
- Customer/site/machine data comes from the detached report snapshot only. It never looks up fresh master records.
- Export is entirely local and includes no browser data, AI endpoint, cloud transfer or credentials.

## Editable Word / DOCX
- Exports real Word Title, heading paragraphs, editable body paragraphs, tabular \`w:tbl\` cells, inline photos/captions and manual page breaks. Nested modules retain original mixed block order; Conclusions are always final.
- Summary entries are generated from the canonical outline and include Word \`PAGEREF\` fields and bookmarks for each section. DOCX fields are marked to be updated on opening, so **Word must update fields after it has repaginated** to display correct page numbers. The initial generated file uses a \`?\` field placeholder rather than inventing static numbers. In desktop Word, select all with Ctrl+A, press F9, and choose to update all fields if prompted. Recheck after editing or printing. This is a genuine dynamic Word field, not a promise that page numbers are known before Word lays out the document.
- The M4 layout follow-up provides repeated Word headers with optional company name and locally selected image logo, a repeated footer with user-provided note and dynamic `PAGE` field. A4 margin reservations separate page furniture from the editable content body. Captions use keep-with-next image anchoring; image display respects maximum printable dimensions and never enlarges low-resolution sources. Arbitrary DOCX floating drawing object editing/template designer remain M6.

## Local PDF
- Uses ReportLab to paginate the **same prepared export projection**, not an external Word or LibreOffice dependency. Rebuilds Summary with multipass page references based on final ReportLab pagination; page footers display current page numbers.
- Exports report information, ordered nested content, local photograph bytes and table cells. Attempts to embed Segoe UI on Windows or DejaVu on Linux when available for better Unicode coverage. Font availability and script shaping remain user-machine acceptance subjects.
- The layout follow-up repeats the same optional name/logo/header and note/footer with local page numbers on every PDF page; photos follow the same bounded physical dimensions as Word. Very tall unsplittable tables and unsupported text may fail with a readable error rather than export partial content.
- PDF is a fixed-format review/print copy, **not** a replacement for editable DOCX.

## Branding and page-layout profile (follow-up PR under review)
- Export branding is configured in the editor using **Export branding**: optional company name, footer note and a user-chosen local PNG/JPEG/WebP/BMP logo. The fields and image path are kept only in local QSettings; logo bytes are read on demand, checked at 2 MiB before decoding, then embedded solely in the selected output. The project archive and browser profile never include them.
- A4 portrait, content body reserves 3.0 cm top/2.5 cm bottom and 2.1 cm sides, with independent header/footer regions. The same `ExportStyle` applies to DOCX and PDF, and the original report remains unchanged. Output may paginate differently between Word and ReportLab.
- Embedded report photos are normalized for EXIF orientation and displayed at natural 96-dpi physical size, limited to 15.6 cm wide and 19.5 cm high; no forced upscaling. Captions are kept adjacent where the renderer permits. Word PAGE and PAGEREF fields may need Ctrl+A/F9 in desktop Word.
- A missing or invalid configured logo fails export visibly and preserves the old file. There is no bundled or invented real company identity. See [ADR-0007](adr/0007-m4-export-presentation-profile.md).

## Safety and failure handling
- Assets are copied only from \`ReportProject.assets\`, validated and converted in memory to bounded PNG; no filesystem paths, remote URLs or unreferenced images enter the export.
- All output goes to a temporary file in the destination directory, then replaces the target only when generation succeeds. A missing/corrupt image or invalid report fails without overwriting an existing output.
- Desktop toolbar has **Export DOCX** and **Export PDF**; graphical Save As dialogs ask before replacing existing output. Invalid pending edits must be resolved before exporting. Export never marks the \`.rmproj\` as saved and never changes its file path.
- Word/PDF dependencies are included in normal desktop install and frozen packaging inputs. The follow-up PR does not publish a new M4 installer; the M0 rolling release stays pinned to its previously approved source.

## Verification
- \`python -m unittest discover -s tests -v\`: synthetic Word XML/field, editable text/table/photo, source project invariants, derived hierarchy, PDF content/page count/outline and atomic failure paths.
- \`python -m reportmaker --export-self-test\`: GUI offline hosted-Windows smoke for export actions, pending form edits, DOCX/PDF files, untouched project source and failure path.
- Native installed-Windows acceptance must exercise actual Word field recalculation, PDF viewing/printing, page wrapping, photo size/orientation, non-Latin text, Windows file dialogs, overwrite prompts and M0–M3 regression checklist. See \`docs/WINDOWS_ACCEPTANCE_M0_M4.md\`.

## Known limitations and deferred scope
- M5: per-block translation UI, missing/stale translation review, different multilingual export layouts, translated report labels.
- M6: arbitrary DOCX template import, user-designed company styles, floating drawing objects and high-fidelity style mapping. Fixed optional header/footer branding is part of the reviewed M4 follow-up.
- M4 PDF may not paginate exactly like Word; the two renderers deliberately share data/structure rather than promising visual page parity.
- Complex scripts, very wide tables, exceptionally deep hierarchies and original high-resolution image detail require additional cross-machine visual tests. Where export cannot safely embed a photo, it fails instead of silently omitting it.
- Installed Windows smoke and independent code review are not yet proven by source CI alone.
