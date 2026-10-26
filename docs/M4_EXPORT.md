# M4 — Editable DOCX and local PDF export (draft PR #13)

Status: source implementation in \`feature/m4-editable-docx-pdf-export\`. Hosted Windows CI and independent review are separate verification gates. **Not an installed-PC acceptance, approved installer, or production release.**

## Source of truth and export boundary
- \`.rmproj\` remains the only canonical editable ReportMaker project. Exports are generated projections; editing a Word document does **not** update the underlying \`.rmproj\`. The user may reopen the project and export again.
- \`prepare_export(ReportProject)\` performs read-only \`validate_report_tree\` and uses \`module_outline(report)\` for section numbers, heading positions and Summary. Contents and tree are not independently persisted.
- Original/source text is used at M4. A report's arbitrarily tagged language records and stale translations are preserved in the project, but automatic translation selection and multilingual presentation are **M5**, not silently emulated through fallback copies in M4.
- Customer/site/machine data comes from the detached report snapshot only. It never looks up fresh master records.
- Export is entirely local and includes no browser data, AI endpoint, cloud transfer or credentials.

## Editable Word / DOCX
- Exports real Word Title, heading paragraphs, editable body paragraphs, tabular \`w:tbl\` cells, inline photos/captions and manual page breaks. Nested modules retain original mixed block order; Conclusions are always final.
- Summary entries are generated from the canonical outline and include Word \`PAGEREF\` fields and bookmarks for each section. DOCX fields are marked to be updated on opening, so **Word must update fields after it has repaginated** to display correct page numbers. The initial generated file uses a \`?\` field placeholder rather than inventing static numbers. In desktop Word, select all with Ctrl+A, press F9, and choose to update all fields if prompted. Recheck after editing or printing. This is a genuine dynamic Word field, not a promise that page numbers are known before Word lays out the document.
- No corporate branding or arbitrary DOCX template import in M4; these are reserved for M6. Word page breaks and photo locations are requested at the proper content position, but final layout depends on Word and fonts.

## Local PDF
- Uses ReportLab to paginate the **same prepared export projection**, not an external Word or LibreOffice dependency. Rebuilds Summary with multipass page references based on final ReportLab pagination; page footers display current page numbers.
- Exports report information, ordered nested content, local photograph bytes and table cells. Attempts to embed Segoe UI on Windows or DejaVu on Linux when available for better Unicode coverage. Font availability and script shaping remain user-machine acceptance subjects.
- PDF is a fixed-format review/print copy, **not** a replacement for editable DOCX.

## Safety and failure handling
- Assets are copied only from \`ReportProject.assets\`, validated and converted in memory to bounded PNG; no filesystem paths, remote URLs or unreferenced images enter the export.
- All output goes to a temporary file in the destination directory, then replaces the target only when generation succeeds. A missing/corrupt image or invalid report fails without overwriting an existing output.
- Desktop toolbar has **Export DOCX** and **Export PDF**; graphical Save As dialogs ask before replacing existing output. Invalid pending edits must be resolved before exporting. Export never marks the \`.rmproj\` as saved and never changes its file path.
- Word/PDF dependencies are included in normal desktop install and frozen packaging inputs. No M4 installer is published by this PR; the M0 rolling release stays pinned to its approved M0 revision.

## Verification
- \`python -m unittest discover -s tests -v\`: synthetic Word XML/field, editable text/table/photo, source project invariants, derived hierarchy, PDF content/page count/outline and atomic failure paths.
- \`python -m reportmaker --export-self-test\`: GUI offline hosted-Windows smoke for export actions, pending form edits, DOCX/PDF files, untouched project source and failure path.
- Native installed-Windows acceptance must exercise actual Word field recalculation, PDF viewing/printing, page wrapping, photo size/orientation, non-Latin text, Windows file dialogs, overwrite prompts and M0–M3 regression checklist. See \`docs/WINDOWS_ACCEPTANCE_M0_M4.md\`.

## Known limitations and deferred scope
- M5: per-block translation UI, missing/stale translation review, different multilingual export layouts, translated report labels.
- M6: branding/template import, headers/logo design and high-fidelity style mapping.
- M4 PDF may not paginate exactly like Word; the two renderers deliberately share data/structure rather than promising visual page parity.
- Complex scripts, very wide tables, exceptionally deep hierarchies and original high-resolution image detail require additional cross-machine visual tests. Where export cannot safely embed a photo, it fails instead of silently omitting it.
- Installed Windows smoke and independent code review are not yet proven by source CI alone.
