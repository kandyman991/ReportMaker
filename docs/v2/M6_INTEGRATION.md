# V2 M6 — Full application integration (in progress)

**Date:** 2026-10-29. **Baseline main:** `63e8d1a359087ddeb2849a17bb961f6c4d995dee` (M5 PR #82). **Branch:** `feature/v2-m6-full-integration`.

## Initial integration slice — implementation ready for independent validation

- A `QTabWidget` separates Modules, Editor, Photo Gallery, ChatGPT and Preview while retaining **exactly one** `ReportSession`, `CommandGateway`, and canonical ordered report hierarchy. V1 application remains untouched.
- Editor uses a bounded 90-row document-style projection (not another report tree); text, photo-caption and table edits stage through `DraftCoordinator.for_editor("page-editor")`. Apply/Revert and existing branch Undo/Redo operate on the same content IDs. Pending drafts block saving/export and destructive navigation; a cross-tab conflict does not overwrite a field.
- Gallery reuses `ProjectPictureList` and the existing validated picture converter. Explicit local-file import, Windows Explorer copy-drop and native image-clipboard paste can create *unplaced* project library assets via an atomic undoable gateway transaction; originals stay unchanged.
- ChatGPT is a lazy, user-operated Qt WebEngine website tab with V1-compatible browser profile configuration and external default-browser fallback. No API, DOM scripts, auto-copy, scraping, chat session data in projects, or report-content transfer.
- Preview is explicitly a **continuous schematic**, derived from `prepare_export` over a detached canonical project, including original report hierarchy and photo visuals. It does not claim pixel-identical Word/PDF pagination.
- DOCX/PDF export uses the existing pure export service with an **explicit V2 Qt visual renderer**. Edited image crops, rotations, annotation marks, per-placement width and alignment are rendered to sanitized detached bytes; unedited project bytes remain immutable. The pure/V1 default still fails closed on edited photos if no renderer is supplied. File export uses existing atomic destination handling.

## Verification and outstanding M6 requirements

- Dedicated synthetic `tests/test_v2_m6.py` includes gallery-only media undo/redo/save/reopen, annotated DOCX/PDF, independent tabs, guarded Editor drafts and branch Undo, stale export prevention and lazy ChatGPT load. Hosted Windows Python 3.11/3.12 steps are wired into `.github/workflows/v2-inline.yml`.
- Report Information toolbar dialog now applies a single validated undoable command for report title, dates/ticket/personnel, customer/site/machine snapshot fields, multiple simultaneous intervention types, and extensible output language tags. Existing referenced customer/site/machine IDs are retained; direct customer-database selection is still outstanding.
- Local template selection now reuses the safe DOCX/DOTX and .rmtemplate importer: validated page dimensions, margins, header/footer text, fonts and embedded logo map into transient ExportStyle for Editor schematic, Preview schematic and actual DOCX/PDF output. Complex unsupported Word objects remain explicitly out of scope; report facts and source template are never modified.
- **Not yet completed:** direct customer database selection, high-fidelity complex Word layout editing and exact export-faithful paginated preview, all-format print fidelity, full installation and accessibility acceptance. These require further M6 slices, tests and review before Checkpoint C can be claimed.
- **Not a release:** native installed Windows 100/125/150% DPI, real browser sign-in/copy/download, touchpad, multi-photo bulk behavior, screen readers and actual Word/PDF visual acceptance remain manual validation gates. V1 fallback and unrelated RC PR #21 are unchanged.

**Next:** review test findings, finish remaining M6 integrations and hosted Windows gates, then request independent PR review before merge. No installer or default-V2 promotion is authorized.
