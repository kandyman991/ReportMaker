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
| **M6.1 — Canonical shared workspaces** | Modules, Editor, Gallery, ChatGPT and Preview are separate tabs over the **same report session** and stable IDs; page Editor drafts have ownership, conflict protection, atomic multi-field Apply and one-step Undo. No duplicate tree, browser automation or lost edits. | **Implemented, hosted CI-tested in #83; review/merge pending.** `v2/app.py`, `editor_tab.py`, `drafts.py`, `commands.py`, `chat_tab.py`; `tests/test_v2_m6.py`, `test_v2_m6_integrity.py`. |
| **M6.2 — Photos, Gallery and faithful basic exports** | Unplaced media imports by local file/Explorer/clipboard remain immutable, undoable and reusable; edited visual placement, captions and text annotations are reflected in DOCX/PDF; exporter fails closed rather than outputting the unedited original. | **Implemented, hosted CI-tested in #83; review/merge pending.** `gallery_tab.py`, `visual_export.py`, `preview_tab.py`, existing audited media/export services; `test_v2_m6.py`, `test_v2_m6_followup.py`. |
| **M6.3 — Report Info and references** | Manual and DB-linked customer/site/machine selection produce frozen consistent snapshots, never edit master records; report title/date/ticket/personnel/multi-type intervention and output-language changes are transactional, undoable and durable. Basic template page/style import included; **complex template fidelity excluded until M6.6**. | **Implemented, hosted CI-tested in #83; review/merge pending.** `report_info.py`, `reference_picker.py`, `storage.py` interface; `test_v2_m6.py`, `test_v2_m6_followup.py`, `test_v2_m6_integrity.py`. |
| **M6.4 — Explicit content translations and language delivery** | Manual stable-ID translation updates, missing/stale/blank prevention, safe source-language provenance, translatable content incl. photo marks, detached language-specific Preview/PDF proof, atomic multi-language DOCX/PDF ZIP export with explicit limitations and no hardcoded language enumeration. **Metadata and boilerplate not yet localized; reserved for M6.5.** | **Implemented, hosted CI-tested in #83; review/merge pending.** `localized_export.py`, `translation_dialog.py`, `pdf_proof.py`, `language_bundle.py`; `test_v2_m6_followup.py`, `test_v2_m6_integrity.py`, `test_v2_m6_bundle.py`. |
| **M6.5 — Metadata and boilerplate localization** | Export titles, headings, TOC labels, report info field labels, intervention type labels, page numbers and any other generated customer-visible strings use the selected export language; customer-entered free-text metadata values have explicit source/translation provenance or a clearly defined intentional-language-neutral policy. No silent English/source fallback. Manual translation workflow and archive manifest must agree. Validate arbitrary BCP-style language tags, save/reopen/Undo and DOCX/PDF parity. **If persistent schema changes, approve an ADR + backward migration first.** | **NOT IMPLEMENTED.** First separate scope-limited PR after #83, stacked on #83 until its approved merge. Do not claim localization from `localized_project` alone. |
| **M6.6 — Precise page Editor and Word/template fidelity** | Content-size text/table layout, accurate supported rich typography, printable page/margin/branding semantics; explicit Word-template compatibility limits, reproducible DOCX/PDF and PDF proof behavior. Test deep/large reports, pagination, annotated media, fidelity and failure handling. Never equate Qt schematic or PDF proof with Microsoft Word pixel-identical rendering without native verification. | **PARTIALLY IMPLEMENTED within #83** (basic styles, natural-height tables, schematic and PDF proof); remainder **not implemented** in its own scoped PR, *after M6.5*. |
| **M6.7 — End-to-end Checkpoint C integration** | One synthetic full report round-trip through Branch Editor, all tabs, customer snapshot, translations, media/annotation, save/reopen, preview, DOCX/PDF and multi-language archive; verified stable IDs, shared derived TOC, no forgotten drafts, valid undo/redo, rollback on errors, persistence backwards-compatibility and Windows hosted gates. Record exact test evidence, independent review and remaining real Windows constraints. | **NOT ACCEPTED.** Dedicated final M6 integration PR/checkpoint review after M6.6. Native installed-Windows DPI, browser login/copy/download and release certification continue into M7. |

## PR ownership and sequencing (mandatory)

1. **PR #83 is frozen for new features** after the formalization/documentation update. It is the **M6.1–M6.4 implementation aggregation** from the work already performed. Only independently reviewed bug fixes, tests required to correct findings, CI repairs, and necessary handoff/docs are allowed. It remains **draft and unmerged** until explicitly authorized. Its eight hosted workflow results are not independent review or native Windows acceptance.
2. **M6.5** uses `feature/v2-m6-5-metadata-localization`, based on PR #83's *frozen final commit*. While #83 is unmerged, create a **stacked draft PR targeting #83's head branch**, so only M6.5 changes appear in its diff. After #83 is approved/merged, retarget or rebase that PR onto the approved `main` baseline and rerun all checks before review/merge.
3. **M6.6** begins only once the previous milestone has a reviewed, CI-clean, agreed baseline. Own branch and independent scoped draft PR; no template or page-editor work inside #83 or M6.5.
4. **M6.7** is the final integration/Checkpoint C PR. It is not permission to release or replace V1.
5. **One active feature slice at a time.** At every boundary: record exact base/head SHA, changed-file scope, synthetic regression matrix, hosted Windows Python 3.11/3.12 checks, missing native Windows evidence, review findings/changes and unresolved risks. Never merge without explicit authorization.

## Immediate next action

Review/freeze PR #83 as the combined M6.1–M6.4 foundation, then perform **M6.5 only**
in its own branch/stacked PR. Before implementing new persistent metadata translations,
document which values are language-neutral, which require source-language provenance,
how undo/redo and schema migration behave, and how both exporters render them.
No hidden machine translation or external AI/browser access.
