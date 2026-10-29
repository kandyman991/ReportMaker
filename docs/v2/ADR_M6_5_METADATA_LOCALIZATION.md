# ADR (Proposed) — M6.5 metadata and generated-label localization

**Status:** Proposed for independent architecture review; **not yet approved**, no schema
or exporter implementation changes in this PR at the time of proposal.
**Date:** 2026-10-29
**Parent milestone:** [M6.5 acceptance plan](M6_SUBMILESTONES.md)
**Review base:** PR #83's frozen M6.1–M6.4 feature branch
`feature/v2-m6-full-integration`.

## Problem and existing behavior

V2 localizes report title, module/heading/paragraph text, table cells, captions
and text photo marks. It does **not** yet localize generated DOCX/PDF/Preview
labels (`Report information`, `Summary`, `Created`, `Page`, etc.),
intervention type labels or the report's user-entered
`other_intervention_detail`. The present `Report` data stores ticket,
technicians and other detail as plain strings; the v4 project serializer
requires exact record keys, and `ExportPlan.info` uses hardcoded English
labels. Merely replacing English labels with one fixed list of supported
languages would violate open-ended language requirements, and silently
retaining English in non-English outputs violates strict customer export.

A change to the canonical project format is therefore unavoidable for durable
manual translations of free-text metadata and custom boilerplate. This ADR
must be approved **before schema-altering implementation**.

## Proposed decision: v5 optional localization ledger (one canonical source)

- Keep existing canonical metadata facts and typed values **unchanged**:
  `ticket`, `technicians`, intervention type codes, all customer/site/machine
  snapshot fields and `other_intervention_detail`. They remain the
  authoritative source. Do not clone the report tree or live-reference the
  customer database at export time.
- Add a single **report-scoped localization ledger** keyed by stable,
  allowlisted semantic keys, *not* by current UI text. Example keys:
  `metadata.other_intervention_detail`, `label.report_information`,
  `label.summary`, `label.report_content`, `label.page`,
  `label.intervention_types`, `intervention.supervision` and every label
  used in `ExportPlan.info`. Each translation record contains exactly:
  `language` (BCP-47-style tag), `text`, and `source_sha256`.
- Derive the source text **on demand** for every key from the single canonical
  report field, or from a versioned, fixed English source-label catalog for
  generated boilerplate. `source_sha256` binds approval to that precise
  source; it does **not** store a second editable source copy. Changing source
  report info or a catalog label automatically makes older translations stale
  without mutating translations in place.
- Explicitly classify values in export:
  * **Language-neutral identifiers and proper names:** ISO dates, ticket
    reference number, machine serial/asset tag, customer, site, machine,
    manufacturer/model and personnel names, addresses and contact values.
    The report snapshot is frozen. These do not require translation or imply
    that names can be auto-translated. The label beside each value **does**.
  * **Translation-required free text:** `other_intervention_detail` when
    `other` is selected and its source is nonempty. When additional free-text
    metadata fields become available, they must be explicitly classified and
    tested before customer export.
  * **Translation-required boilerplate:** all customer-visible generated
    headings, metadata field labels, intervention type descriptions, TOC/summary
    labels and page-number prefix used in DOCX, PDF, schematic and proof. Every
    customer-visible label must have a semantic key; no scattered hardcoded
    English presentation strings.
- **No automatic translation, language-enum restriction, network access or
  silent locale fallback.** Exact target-language tags must resolve from
  reviewed user-edited entries or explicitly shipped catalog translations.
  Source-English output can use canonical catalog originals when the selected
  source label language is English. Other languages with gaps fail closed
  before changing the destination file; project save/reopen is independent
  of whether translations are complete.
- Changes to ledger entries go through `CommandGateway` with stable keys,
  generation/revision guards, single-step Undo/Redo, draft conflict handling,
  provenance checks and unchanged source metadata. Report Information
  modifications may mark existing entries stale through digest mismatch.
- Render boilerplate using an explicit detached export-locale context used by
  `prepare_export`, both DOCX/PDF writers, the Preview tab and PDF proof.
  The multilingual ZIP reuses the same context for each member; the
  `manifest.json` description must no longer misleadingly report English
  labels for languages validated under this policy. Source export remains
  backwards compatible.

## v5 wire format and migration (subject to approval)

- Upgrade `reportmaker.project` from format **v4 to v5** only when this
  ledger implementation is accepted. Add required, strictly bounded
  `report.localization_ledger` (empty map allowed) in v5; keep all old v4
  record fields and frozen snapshot representation unchanged. Use the existing
  duplicate-key rejection, UTF-8 JSON, 8 MiB manifest bound and atomic file
  save behavior. Reject invalid/unrecognized keys, duplicate language tags
  differing only by case, malformed SHA-256, excessive entry lengths/counts
  and future unknown schema versions.
- Load legacy v1–v4 unchanged into memory with an empty ledger; preserve
  original metadata, stable IDs, assets, links, text translations and photo
  annotations exactly. **No synthetic translation is invented.**
  Legacy source-language output still works. Selected non-English export now
  demands explicit metadata localization, even if report body translations
  are otherwise complete.
- For legacy files, existing `ReportProject.loaded_version` and
  `loaded_from` continue enforcing **Save As** to a new v5 file, never
  overwriting the user's v1–v4 original. No promise that V1 can reopen v5.
  Validate old-file round trips and reject corrupt v5 before session swap.
- Add an explicit project compatibility notice when writing v5 for V2.
  Language-neutral original project facts and foreign translations must
  remain stable through Save As, reopen, Undo/Redo and repeated exports.

## Rejected approaches

1. **Hardcoded language enum** (e.g., only English/Italian): does not allow
   arbitrary language tags and risks silent fallbacks.
2. **Duplicated localized customer database or shadow ReportInfo model:**
   breaks canonical truth and snapshot/reference consistency.
3. **In-memory-only localized labels:** lost on project reopen and not
   reproducible on another machine.
4. **Machine translation/browser injection:** prohibited browser boundary
   and non-deterministic customer export.
5. **Changing v4 records without format bump:** older parsers' strict shape
   validation would misinterpret or reject files without clear migration.

## M6.5 implementation/acceptance checklist (not yet passed)

- [ ] Reviewed ADR decision and exact v5 wire schema.
- [ ] Stable semantic key registry, locale ledger, safe validation and command
      transactions with stale-source rejection and Undo/Redo.
- [ ] v1–v4 load + non-destructive Save As v5, future/corrupt rejection,
      stable IDs/assets/customer snapshots and V1 compatibility warning.
- [ ] User-operated translation editing for metadata and labels; no machine
      translation or UI-locale coupling.
- [ ] DOCX, PDF, Qt schematic, PDF proof and ZIP render all customer-visible
      generated headings/labels/types/page numbering from the same locale
      context with no English fallback.
- [ ] Synthetic complex multi-type and other-detail reports with arbitrary
      language tags, Unicode, missing/stale/blank translations,
      intervening metadata changes, archive rollback and proof consistency.
- [ ] Hosted Windows Python 3.11 and 3.12 affected M1–M6 checks pass on
      exact final head; independent review and explicit merge authorization.
- [ ] M6.6 fidelity and M6.7 final Checkpoint C remain outside this PR.

**Architecture boundaries:** This ADR does not authorize ChatGPT API access,
browser DOM/cookie reading, customer-data uploads, a second report model, V1
shell rewrites or M6.6 Word/page work. Native installed-Windows release
acceptance remains M7.
