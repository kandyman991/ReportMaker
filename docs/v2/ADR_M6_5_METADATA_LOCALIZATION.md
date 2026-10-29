# ADR (Proposed) — M6.5 metadata and generated-label localization

**Status:** Independently reviewed with corrective design constraints (2026-10-29); accepted as the v5 implementation contract, **not** as approval to merge, ship or claim M6.5 feature completion. Persisted schema changes require their own implementation/regression review.
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
- Add a single **report-scoped localization ledger** for **project-owned source keys** keyed by stable,
  allowlisted semantic keys, *not* by current UI text. Example keys:
  `metadata.other_intervention_detail`, `label.report_information`,
  `label.summary`, `label.report_content`, `label.page`,
  `label.intervention_types`, `intervention.supervision` and every label
  used in `ExportPlan.info`. Each translation record contains exactly:
  `language` (BCP-47-style tag), `text`, and `source_sha256` (the key and language are map keys in the proposed wire representation). Transient template branding is **not** an allowed persisted ledger key.
- Derive source text **on demand** from its canonical metadata field or from
  a versioned English source-label catalog. **Generated label source is always
  `en`, independent of `Report.primary_language`.** The source digest binds
  key + source language + exact source text, not text alone; changes make
  existing approvals stale without storing a second editable source copy.
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
    labels and page-number prefix used in DOCX, PDF, schematic and proof;
    Preview-only summary explanation, manual-page-break placeholder and footer
    prefix must also have source keys, derived from canonical visible content. Every
    customer-visible label must have a semantic key; no scattered hardcoded
    English presentation strings.
  * **Branding-specific text:** a company name/logo are language-neutral
    identifiers; a nonempty authored `ExportStyle.footer_note` is customer
    prose. Because `ExportStyle` is transient and not part of `.rmproj`,
    `branding.footer_note` approvals may be supplied **only in detached export
    context**, never persisted in the report ledger. The user must explicitly
    declare the source language of this imported/authored footer; never infer
    it from `Report.primary_language`. For another output language require an
    approved source-digest-bound variant or reject export atomically. Do not
    persist transient branding inside the customer snapshot. Durable per-project
    template design/locale storage remains M6.6.
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

## v5 wire format and migration (reviewed implementation contract)

- Upgrade `reportmaker.project` from format **v4 to v5** during M6.5 implementation,
  after preserving this reviewed contract and adding targeted gates. Add required, strictly bounded
  `report.localization_ledger` (empty map allowed) in v5; keep all old v4
  record fields and frozen snapshot representation unchanged. **Do not** merely
  change `VERSION = 4` to `5`: the loader currently checks
  `require_rich=(manifest.version == VERSION)` and that would break v4.
  Define a separate `RICH_FORMAT_VERSION = 4` and accept versions 1–5;
  v4/v5 both require rich typography, and v3–v5 require photo visual state.
  Media-library checks must still cover v2–v5 and legacy records must reject
  v5-only keys. Use the existing
  duplicate-key rejection, UTF-8 JSON, 8 MiB manifest bound and atomic file
  save behavior. Reject invalid/unrecognized keys, duplicate language tags
  differing only by case, malformed SHA-256, excessive entry lengths/counts
  and future unknown schema versions.
- **Exact new report record:** for version 5, add required
  `report.localization_ledger` as an object of recognized **persistable**
  semantic keys (`PERSISTABLE_KEYS`) to an object mapping validated language
  tags to records of exactly `{"text": string, "source_sha256": lowercase_64_hex}`.
  No redundant copied source, key or language fields; no client-controlled
  catalog changes; no unknown properties, duplicates, case-variant language
  duplicates, invalid XML 1.0 text, source-language overrides, or source-blank
  fabricated approvals. An empty object is valid. Existing v1–v4 records
  must **reject** this new property instead of silently ignoring it. The
  transient `branding.footer_note` key is **prohibited** in persisted records,
  because its style source text and source language are not portable today.
  A language-neutral footer is never inferred merely because a translation
  is missing.
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

## Independent architecture and foundation review findings (2026-10-29)

1. **HIGH — v4 rich-text compatibility:** a naïve VERSION bump breaks v4 decoding because the loader ties rich-text requirements to the current version. Define independent per-feature minimum versions and test v1–v5 migrations before changing persistence.
2. **HIGH — source-language confusion:** boilerplate has an English source even for reports authored in other languages; it must never inherit the report's primary-language tag.
3. **MEDIUM — branded footer:** user-entered footer prose may need translation; never treat it as an automatically language-neutral proper name.
4. **MEDIUM — untrusted provenance and malformed Unicode:** digest must bind key, source language and text. Reject unknown/nonstring keys, duplicate locale casing, blank source/target inventions, malformed Unicode/XML characters and oversize values; stale entries may be stored, but cannot be resolved for customer export.
5. **HIGH — ephemeral template footer provenance:** a report-local approval for transient `ExportStyle.footer_note` cannot be reliably replayed after reopen or style replacement. Prohibit its wire persistence; require declared independent source language and pass transient approvals to detached export context.
6. **MEDIUM — Preview generated-label coverage:** the early registry omitted preview-only summary guidance, manual page break and footer prefix. Catalog them and derive required keys from the canonical report tree, including nested modules.
7. **MEDIUM — exact-head CI blind spot:** path-limited staged Windows workflows can skip future schema/editor/docs-only branch heads; enforce head-branch gates without path filtering and retain Python 3.11/3.12.

**Review disposition:** The ADR is accepted **for implementing** the scoped v5 migration, with the wire schema and transient-branding exclusion above. No migration, UI/export changes or complete M6.5 acceptance exist in the present code; all still require implementation review, exact-head Windows CI and explicit user authorization before merge. Do not treat ADR acceptance as a passing feature gate.
