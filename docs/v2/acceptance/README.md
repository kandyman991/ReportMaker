# PR #88 — Synthetic desktop Microsoft Word acceptance sample

These binary artifacts were exported from the **reviewed M6.6 implementation**
at `3e4127518e8befe75fecea45cd41b972efdbb066` by calling
`reportmaker.export.export_project` directly (no installed ReportMaker V2 UI).

- `pr88-synthetic-a4.docx` — editable Word report
- `pr88-synthetic-a4.pdf` — independently rendered PDF proof for visual comparison

Both use fictional intervention data and a programmatically generated test
image. No customer documents, customer photos, or browser information appear.

**On Windows with Microsoft Word:** download both files. Open the DOCX in
Microsoft Word Print Layout, enable editing if prompted, select body text and
update its fields with `Ctrl+A` then `F9` (on some laptops `Fn+F9`).
Inspect report info, TOC page references, margins, nested module headings,
numbered list, photo/arrow, 5-column table, manual page break, page footer
and Conclusions. Open the PDF separately for a second-renderer comparison.
The physical page counts do not need to match. Report any incorrect margins,
overlaps, errors in references, cropped images/tables, or broken pagination.

For strict automated field/page-count checking, download
`scripts/verify_word_pagination.ps1` from PR #88 and run it as specified in
`docs/v2/M6_6_WORD_ACCEPTANCE.md`. The script requires a local desktop
Microsoft Word installation, not an installed ReportMaker V2 application.

This QA fixture is on an **independent branch**, not merged or added to PR #88.
The sample does not certify Microsoft Word rendering until someone actually
opens and inspects it in native Word.
