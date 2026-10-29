# M6 — Formal submilestone and pull-request contract

**Approved work decomposition:** 2026-10-29, during V2 M6 implementation.
**Parent milestone:** [ROADMAP.md](ROADMAP.md#M6--full-application-integration), Checkpoint C.
**Implementation baseline:** PR [#83](https://github.com/kandyman991/ReportMaker/pull/83) at tested code head
`84135cacd2a415800fc723298a13ad19a5f23c5f` (8/8 hosted workflows successful).
**Status vocabulary:** *implemented / CI-tested* means code and hosted synthetic tests exist; it does
**not** mean independently approved, merged, native-Windows accepted or released.

This document divides M6 into **seven sequential review/PR boundaries**, without altering
AGENTS.md, ARCHITECTURE.md, docs/v2/ARCHITECTURE.md or the previously approved M6
Checkpoint C definition. The Branch Editor remains primary; there is exactly one canonical
`ReportSession` and one report hierarchy/TOC. ChatGPT is an independent, manually operated
website-only browser tab.

## Workstream / evidence matrix (baseline PR #83)

| Slice | Objective and acceptance | PR evidence and verified state |
| --- | --- | --- |
| **M6.1 — Canonical shared workspaces** | Modules, Editor, Gallery, ChatGPT and Preview are separate tabs over the **same report session** and stable IDs; page Editor drafts have ownership, conflict protection, atomic multi-field Apply and one-step Undo. No duplicate tree, browser automation or lost edits. | **Reviewed and merged into main in #83, 2026-10-29.** `v2/app.py`, `editor_tab.py`, `drafts.py`, `commands.py`, `chat_tab.py`; `tests/test_v2_m6.py`, `test_v2_m6_integrity.py`. |
| **M6.2 — Photos, Gallery and faithful basic exports** | Unplaced media imports by local file/Explorer/clipboard remain immutable, undoable and reusable; edited visual placement, captions and text annotations are reflected in DOCX/PDF; exporter fails closed rather than outputting the unedited original. | **Reviewed and merged into main in #83, 2026-10-29.** `gallery_tab.py`, `visual_export.py`, `preview_tab.py`, existing audited media/export services; `test_v2_m6.py`, `test_v2_m6_followup.py`. |
| **M6.3 — Report Info and references** | Manual and DB-linked customer/site/machine selection produce frozen consistent snapshots, never edit master records; report title/date/ticket/personnel/multi-type intervention and output-language changes are transactional, undoable and durable. Basic template page/style import included; **complex template fidelity excluded until M6.6**. | **Reviewed and merged into main in #83, 2026-10-29.** `report_info.py`, `reference_picker.py`, `storage.py` interface; `test_v2_m6.py`, `test_v2_m6_followup.py`, `test_v2_m6_integrity.py`. |
| **M6.4 — Explicit content translations and language delivery** | Manual stable-ID translation updates, missing/stale/blank prevention, safe source-language provenance, translatable content incl. photo marks, detached language-specific Preview/PDF proof, atomic multi-language DOCX/PDF ZIP export with explicit limitations and no hardcoded language enumeration. **Metadata and boilerplate not yet localized; reserved for M6.5.** | **Reviewed and merged into main in #83, 2026-10-29.** `localized_export.py`, `translation_dialog.py`, `pdf_proof.py`, `language_bundle.py`; `test_v2_m6_followup.py`, `test_v2_m6_integrity.py`, `test_v2_m6_bundle.py`. |
| **M6.5 — Metadata and boilerplate localization** | Export titles, headings, TOC labels, report info field labels, intervention type labels, page numbers and other customer-visible generated strings use the approved output language; customer-entered free-text metadata has source/translation provenance; proper names, dates, tickets and frozen reference fields remain neutral. No silent English/source fallback. Manual translation workflow, PDF proof and ZIP manifest agree. Open-ended language tags, v1–v4 Save As, Undo/Redo and DOCX/PDF parity are required. | **Reviewed, corrected and merged into main in PR #84 on 2026-10-29.** Reviewed v5 ADR, v5 ledger/serializer, metadata translation command/UI, transient branding approvals, strict exports and synthetic Windows Python 3.11/3.12 regressions. See `M6_5_PROGRESS.md`. Not yet accepted or merged. |
| **M6.6 — Precise page Editor and Word/template fidelity** | Content-size text/table layout, accurate supported rich typography, printable page/margin/branding semantics; explicit Word-template compatibility limits, reproducible DOCX/PDF and PDF proof behavior. Test deep/large reports, pagination, annotated media, fidelity and failure handling. Never equate Qt schematic or PDF proof with Microsoft Word pixel-identical rendering without native verification. | **ACTIVE in dedicated M6.6 draft branch** after #84 merge. Initial geometry and fixed DOCX table slice in progress; additional Word template/typography/stress/native tests are outstanding. See `M6_6_PROGRESS.md`. |
| **M6.7 — End-to-end Checkpoint C integration** | One synthetic full report round-trip through Branch Editor, all tabs, customer snapshot, translations, media/annotation, save/reopen, preview, DOCX/PDF and multi-language archive; verified stable IDs, shared derived TOC, no forgotten drafts, valid undo/redo, rollback on errors, persistence backwards-compatibility and Windows hosted gates. Record exact test evidence, independent review and remaining real Windows constraints. | **NOT ACCEPTED.** Dedicated final M6 integration PR/checkpoint review after M6.6. Native installed-Windows DPI, browser login/copy/download and release certification continue into M7. |

## PR ownership and sequencing (mandatory)

1. **PR #83 is merged** into main at `ec27693819a72afb72d24464e803b112ae6aec9a` after independent review and exact-head hosted CI. It remains the historical **M6.1–M6.4 implementation aggregation**, not M6 Checkpoint C or native Windows release acceptance.
2. **M6.5 is merged** into `main` in reviewed PR #84 at `42806a3f0ecef0c3cd5f1c8ff34e0129f25efdce`, preserving v5 metadata approvals and separate transient branding.
3. **M6.6** begins from post-M6.5 main `e2b19d0a5fea6db6d211d1f306c657969dcc177f` in the dedicated `feature/v2-m6-6-page-word-fidelity` draft branch. Initial geometry and DOCX table changes are only an early milestone slice. Finish rich typography, template, large-report and independent Windows/Word evidence before acceptance; do not put M6.6 changes in #83/#84.
4. **M6.7** is the final integration/Checkpoint C PR. It is not permission to release or replace V1.
5. **One active feature slice at a time.** At every boundary: record exact base/head SHA, changed-file scope, synthetic regression matrix, hosted Windows Python 3.11/3.12 checks, missing native Windows evidence, review findings/changes and unresolved risks. Never merge without explicit authorization.

## Immediate next action

PR #83 (M6.1–M6.4) and PR #84 (M6.5) are merged. M6.6 has begun in its
own isolated branch with responsive paper geometry and fixed printable Word
table widths. Finish remaining scoped fidelity acceptance, independent review
and exact-head hosted Windows CI before considering merge. M6.7 and installed
Windows release acceptance remain separate. No browser/API automation.
