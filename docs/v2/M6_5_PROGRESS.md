# M6.5 — Metadata and generated-label localization implementation checkpoint

**Date:** 2026-10-29. **PR:** [#84](https://github.com/kandyman991/ReportMaker/pull/84), stacked on frozen M6.1–M6.4 [PR #83](https://github.com/kandyman991/ReportMaker/pull/83).

## What is implemented

- Pure `v2/metadata_locale.py` defines allowlisted stable semantic keys for generated report headings, report-info labels, intervention types, page prefix and Preview-only summary/break/footer text. The report-owned free-text key covers `other_intervention_detail`; transient `branding.footer_note` is separately tagged and **prohibited in the future persisted ledger** because the associated `ExportStyle` is not saved in a project. All labels are assigned a fixed **English source language**, independently of `Report.primary_language`.
- `LocaleApproval` is a frozen, reviewable entry binding semantic key, target language, text and SHA-256 of key/source-language/source-text. The resolver validates arbitrary language tags and rejects malformed/nonstring keys, case-variant duplicate language entries, bad digests, overlong or XML-incompatible Unicode text, forged target-only metadata and blank translations. Source revisions and explicitly declared branded-footer source languages change digest provenance; stale approvals cannot be exported.
- `visible_metadata_keys` derives necessary generated labels from canonical report fields and nested/manual-break structure, not a second report tree; `resolve_many` supports all-or-nothing validation before customer output.
- 20 synthetic tests in `tests/test_v2_m65_catalog.py` cover English catalog independence, Unicode/arbitrary tags, stale source edits, source-language relabeling, blank/missing/outdated/invisible-only translation refusal, malformed or oversized source metadata, invalid XML characters/surrogates, untrusted keys, fabricated translations, independent footer language, preview-only nested breaks, source digest identity, canonical preservation and unchanged **v4 project save/load**.
- Added the stacked PR head branch to hosted Windows Python 3.11/3.12 `v2-inline.yml` and included the new suite in compileall and regression steps. Dedicated staged workflow now runs without path filters for every branch push and this PR's head (including docs-only changes), avoiding blind spots in exact-head gates.

## Explicitly NOT implemented or approved yet

- **No v5 schema changes.** `project_io.VERSION` remains 4, with unchanged v1–v4 loading and V1 compatibility. `LocaleApproval` is not persisted and is not wired into `ReportProject` yet.
- **No changes to production DOCX/PDF, Preview, PDF proof, ZIP output or manual Report Information UI.** They must not be reported as fully localized; existing English/source boilerplate remains a documented limitation.
- The [reviewed ADR](ADR_M6_5_METADATA_LOCALIZATION.md) now specifies exact project-owned v5 ledger encoding, v3/v4 feature-specific decoding thresholds, explicit template-footer source language and transient-only branding approvals. Independent architecture review **accepts this contract for further v5 implementation only**; migration, UI, export and final PR acceptance still require implementation and regression reviews.
- M6.6 page/Word fidelity and M6.7 Checkpoint C remain outside this PR. No merge, release or native installed-Windows acceptance authorized.

## Next acceptance gate

Implement **only M6.5** ledger persistence, validated canonical commands, manual UI and strict DOCX/PDF/Preview/PDF-proof/ZIP integration against the reviewed ADR, with full backward migration and Windows CI. The present PR is still only a review-corrected **pre-schema foundation**, not a finished milestone. Retarget PR #84 onto main only after PR #83 is explicitly approved and merged. No automatic translation or browser integration.

## Independent code review corrections — 2026-10-29

| Finding | Severity | Correction |
| --- | --- | --- |
| R1: generated Preview report text omitted from semantic catalog | Medium | Added dedicated Preview keys; nested page breaks are discovered from canonical report tree; synthetic coverage |
| R2: untrusted translations could carry XML-invalid chars and unhashable semantic keys | High | Validate XML 1.0-safe Unicode on approval/replay, source metadata and source digests; reject malformed key types and visually invisible-only entries; regressions |
| R3: forged target-only entries from an empty free-text source could resolve | High | Reject creation of approvals from blank sources and fail closed on forged persisted-shape approvals; regressions |
| R4: transient branding approvals would be mis-labeled/persisted across templates | High | Require explicit footer source language; separate transient and persistable keys; v5 wire contract excludes branding |
| R5: path-filtered staged CI could skip exact-head checks | Medium | Run dedicated 3.11/3.12 gate on every M6.5 branch push and stacked PR regardless of changed path |
| R6: duplicate/oversized locale resolution requests could bypass expected bounded contract | Medium | Enforce finite unique allowlisted key sequences; synthetic regression |

**Review baseline:** `8232a9c1fc31dfce87436d56da4e48affc371d3d`. **Corrective review:** [PR #84](https://github.com/kandyman991/ReportMaker/pull/84), exact current head and Windows status must be checked live. No current .rmproj version bump, no merger, no installed Windows acceptance claim.
