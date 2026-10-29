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


## Continued implementation — local references, translations, PDF proof (2026-10-29)

**Implementation checkpoint:** `ee45c7f86cd7b187d9507bb45a5d738d19e895ac`. Windows hosted CI at this code revision: **all 8 workflows passed**, including dedicated Windows Python 3.11 and 3.12 M6 regression suites, M1–M5 V2 gates, core model/export gates, and V1 customer UI smoke. This is NOT physical installed-Windows validation.

- **Database-linked selection:** Read-only customer/site/machine search in the existing local `CustomerStore`; selection reads a detached, consistent snapshot. The dialog only stages the snapshot; applying Report Information uses a single validated gateway transaction to update the snapshot and `report.customer_id` together. Switching to manual mode removes master IDs but retains other frozen customer/site/machine address and contact details. Undo/Redo, Save/Open, mismatch rejection and late master-data changes have synthetic tests.
- **Explicit language editing:** `set_translation` applies only to stable report fields through the existing command gateway. A manual Translations dialog lets users edit title, module titles, paragraphs/headings, table cells, photo captions and textual photo annotations. Original wording and translation provenance remain in the canonical .rmproj; edits are undoable and ownership/draft conflicts remain guarded.
- **Strict selected-language output:** A detached `localized_project` projection fails closed on missing, stale, unselected or invalid translated fields. The Preview language selector and DOCX/PDF use that same projection, including photo-mark text. No machine translation, fallback language substitution or modification of the user's original project is performed. **Limitation:** report-information values and boilerplate labels are still displayed as stored/English; translated output here refers to translatable content fields, not full localized metadata/labels.
- **Paginated PDF proof:** The Preview tab now has an explicit PDF-proof action using the same local exporter, bounded 80 MiB QBuffer and QtPdf page renderer. It displays actual PDF pages and invalidates after a canonical edit or changed template/language. The fast schematic preview remains separate. Microsoft Word's DOCX pagination is **not** claimed to match the PDF proof.
- Regression coverage: `tests/test_v2_m6_followup.py` added to the Windows 3.11/3.12 CI. Only synthetic database content and fabricated images are used; no private customer files or browser profiles are committed.

**Still outstanding for full M6 Checkpoint C:** fully translated metadata/boilerplate/report-information language workflow; high-fidelity complex imported Word layout editing, precise page Editor typography/geometry and actual DOCX/Word page fidelity; multi-output language presentation modes; broader end-to-end/migration acceptance; native installed-Windows DPI/clipboard/browser/login and Word/PDF visual checks. Keep PR #83 **draft and unmerged**, retain V1 fallback and RC PR #21 unchanged.
