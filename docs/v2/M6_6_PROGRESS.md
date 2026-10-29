# M6.6 — Precise Page Editor and Word/template fidelity

**Status:** Started on isolated draft branch `feature/v2-m6-6-page-word-fidelity`; **not independently accepted or merged**. Baseline is post-M6.5 `main` at `e2b19d0a5fea6db6d211d1f306c657969dcc177f`. Follow-up to [issue #86](https://github.com/kandyman991/ReportMaker/issues/86) and the [formal M6 contract](M6_SUBMILESTONES.md).

## Acceptance and non-negotiable contracts

- Keep the report in the one canonical `ReportSession`/ordered hierarchy; no parallel page or TOC model, no schema changes. A Word template is an untrusted **layout profile**, never a second report or imported DOCX body.
- Editor's continuous paper is an **editable schematic** over the same canonical blocks. It must fit narrow app panels, grow to contain text/tables and never show nested scrollbars; paper geometry is not a promise of Word pagination.
- Exported DOCX must be genuinely editable. Word table widths and basic text styles must respect printable margins; the PDF writer and QtPdf proof remain the authority for **PDF** page count, never for Word page count.
- Preserve Word-specific capabilities/limits visibly. Complex Word templates with headers of multiple columns, shapes, floating objects, section-specific styles, text boxes and installed font differences are not copied verbatim. Never silently claim unsupported fidelity.
- Keep multilingual translations, customer snapshots, photos/marks, browser-only ChatGPT, V1 compatibility, atomic overwrite and the private-data boundary intact. No M6.7 checkpoint or installer promotion.

## M6.6-A implemented: paper metrics and fixed Word table layout

1. `NaturalPagePaper` computes the full physical-paper outline and **all four editable-page margins from one cm-to-pixel scale**; it scales at narrow widths without the former hard-coded 500-pixel minimum or independently clamped margins. The outer page remains continuous; only real DOCX/PDF export determines pagination.
2. The Page Editor adopts the selected Word profile's **base normal and heading font families/sizes**, preserving the source rich runs in the canonical model. Advanced inline typography must be controlled in the Branch formatting toolbar until further M6.6 validation.
3. `NaturalPageTable` recomputes its natural height as cell text changes, retaining no inner scrolling.
4. Editable DOCX Report Information and content tables have **fixed, explicit column/grid/cell widths** derived from selected printable width, aligned with the PDF table sizing policy. `w:tblLayout` and `w:tblW` no longer rely on Word autofit to keep data within imported margins. We do **not** assume the first user table row is a header.
5. Added `tests/test_v2_m66_fidelity.py`: Word OOXML grid and margin verification, multi-page PDF with wide/long tables, narrow Qt paper scaling, table growth and canonical text-preservation font checks. Hosted Windows Python 3.11/3.12 dedicated `v2-m66-fidelity.yml` plus the broader V2 regression workflow are mandatory checks on this draft.

## M6.6 remaining before milestone acceptance

- Verify richer paragraph-run styling, list/line spacing, text and heading flow, page-break behavior and printable overflow in exported Word on a *native installed Windows + Microsoft Word* environment; document Word field-update/pagination differences. Add reproducible XML checks for supported constructs and fail-closed paths.
- Expand synthetic stress gates for deeper/large reports, embedded photos/marks, oversized table rows, narrowly constrained templates, multilingual fonts, preview/proof invalidation and failure atomicity. Template import intentionally remains allowlisted; unsupported objects require warnings instead of guessed reconstruction.
- Independently review this entire milestone branch for architecture, layout, data integrity and regression impact, fix findings, and verify exact-final-HEAD GitHub-hosted Windows CI before any proposed merge.
- **No release or M6.7 promotion**. The user has authorized starting development, not merging this new PR.
